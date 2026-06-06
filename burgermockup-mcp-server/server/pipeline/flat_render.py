"""Flat render path: upscale base → composite design into the annotated quad
→ integrity-gate → retry without shading → store. The gate is inside this
function — callers cannot skip it, and nothing below the internal threshold
is ever returned as a usable mockup."""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np
from PIL import Image

from server.pipeline import metrics
from server.pipeline.compositor import composite
from server.pipeline.ssim_gate import score, threshold_for
from server.pipeline.upscale import upscale_base
from server.storage import file_store

_SHADING_DEFAULT = 0.85

_log = logging.getLogger(__name__)


class GateFailure(Exception):
    """Composite failed integrity verification even on the flat-paste retry."""


def _load_rgba(path: str) -> np.ndarray:
    return np.array(Image.open(path).convert("RGBA"))


def flatten_over_white(rgba: np.ndarray) -> np.ndarray:
    """White-composite an RGBA image and return it fully opaque (same shape).

    Catalog bases carry dark RGB values hidden under near-zero alpha (matting
    remnants from the source photos). Any naive alpha-dropping conversion
    (cv2 RGBA2RGB, PIL convert("RGB")) exposes them as gray blotches, so the
    base is flattened over white ONCE at load — downstream upscale, shading,
    scene-model input, and save then operate on clean opaque pixels. Designs
    must NOT pass through this: their alpha drives compositing."""
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    out = rgba.copy()
    out[:, :, :3] = (rgba[:, :, :3].astype(np.float32) * a
                     + 255.0 * (1.0 - a)).astype(np.uint8)
    out[:, :, 3] = 255
    return out


def render_flat(design_path: str, base_path: str,
                quad: list[tuple[float, float]], *,
                text_heavy: bool = False, prompt: str = "",
                mockup_id: str = "", design_scale: float = 1.0) -> dict:
    """Returns {file_id, ssim, cost_usd}; raises GateFailure when the design's
    integrity cannot be preserved. Deterministic, CPU-only, no paid calls."""
    t0 = time.time()
    design = _load_rgba(design_path)
    base = flatten_over_white(_load_rgba(base_path))
    up_base, up_quad = upscale_base(base, quad)

    threshold = threshold_for("flat", text_heavy)
    ssim = 0.0
    # First pass with fabric shading; shading=0 retry recovers designs whose
    # fine detail the shading multiply degrades.
    for strength in (_SHADING_DEFAULT, 0.0):
        result = composite(design, up_base, up_quad, shading_strength=strength,
                           design_scale=design_scale)
        try:
            ssim = score(result.canvas, result.image, result.forward_m)
        except np.linalg.LinAlgError:
            raise GateFailure("print quad is degenerate; cannot verify integrity")
        _log.debug("flat gate ssim=%.4f threshold=%s shading=%.2f",
                   ssim, threshold, strength)
        if ssim >= threshold:
            file_id, _ = file_store.save_image(
                Image.fromarray(cv2.cvtColor(result.image, cv2.COLOR_RGBA2RGB)))
            metrics.log_variant(mockup_id or file_id, prompt, "flat-cv", ssim,
                                int((time.time() - t0) * 1000), 0.0)
            return {"file_id": file_id, "ssim": round(ssim, 4), "cost_usd": 0.0}
        if strength != 0.0:
            _log.info("flat gate below threshold (%.4f < %s); "
                      "retrying without shading", ssim, threshold)

    metrics.log_variant(mockup_id or "rejected", prompt, "flat-cv", ssim,
                        int((time.time() - t0) * 1000), 0.0)
    raise GateFailure(f"integrity below threshold ({ssim:.3f} < {threshold})")

"""Flat render path: upscale base → composite design into the annotated quad
→ store. Deterministic, CPU-only, no paid calls."""

from __future__ import annotations

import logging
import time

import cv2
import numpy as np
from PIL import Image

from server.pipeline import metrics
from server.pipeline.compositor import composite
from server.pipeline.upscale import upscale_base
from server.storage import file_store

_SHADING_DEFAULT = 0.85

_log = logging.getLogger(__name__)


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


def compose_flat_image(design_path: str, base_path: str,
                       quad: list[tuple[float, float]], *,
                       design_scale: float = 1.0) -> np.ndarray:
    """Design composited onto the upscaled flat base; returns the RGBA array.

    Pure compute — no file_store/metrics side effects — so the flat path and
    the on-model path (which sends this image to the scene model) share one
    compositing implementation."""
    design = _load_rgba(design_path)
    base = flatten_over_white(_load_rgba(base_path))
    up_base, up_quad = upscale_base(base, quad)
    result = composite(design, up_base, up_quad,
                       shading_strength=_SHADING_DEFAULT,
                       design_scale=design_scale)
    return result.image


def render_flat(design_path: str, base_path: str,
                quad: list[tuple[float, float]], *,
                prompt: str = "", mockup_id: str = "",
                design_scale: float = 1.0) -> dict:
    """Returns {file_id, cost_usd}. Deterministic, CPU-only, no paid calls."""
    t0 = time.time()
    image = compose_flat_image(design_path, base_path, quad,
                               design_scale=design_scale)
    file_id, _ = file_store.save_image(
        Image.fromarray(cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)))
    metrics.log_variant(mockup_id or file_id, prompt, "flat-cv",
                        int((time.time() - t0) * 1000), 0.0)
    return {"file_id": file_id, "cost_usd": 0.0}

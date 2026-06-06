"""CV compositor: place the ORIGINAL design onto the print quad so it looks
printed (perspective + fabric shading) while staying pixel-faithful. The
design is only ever geometrically transformed and lit — never redrawn.

Key invariants:
- single resample: the design is letterboxed into a quad-aspect canvas by
  PASTE (no resampling), then warped exactly once into the base.
- shading map is normalized around 1.0 (divided by its in-quad mean) so it
  adds fabric light/shadow without darkening designs on dark garments.
- emits the forward homography + warped alpha mask; the integrity gate inverts
  THIS transform instead of re-detecting the design's position.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CompositeResult:
    image: np.ndarray        # RGBA mockup
    forward_m: np.ndarray    # 3x3 homography: canvas coords -> mockup coords
    canvas: np.ndarray       # the letterboxed design (RGBA) that was placed
    warped_alpha: np.ndarray # design alpha in mockup coords (float 0..1)


def _letterbox(design_rgba: np.ndarray, quad: list[tuple[float, float]],
               design_scale: float = 1.0) -> np.ndarray:
    """Paste the design centered into a transparent canvas whose aspect ratio
    matches the quad — fit-within, never stretch-distort. Pure paste: no
    resampling happens here. design_scale < 1 shrinks the PRINTED size by
    enlarging the canvas around the untouched design pixels, so scaling costs
    zero extra resamples (the single warp absorbs it)."""
    dh, dw = design_rgba.shape[:2]
    qw = max(np.hypot(quad[1][0] - quad[0][0], quad[1][1] - quad[0][1]),
             np.hypot(quad[2][0] - quad[3][0], quad[2][1] - quad[3][1]))
    qh = max(np.hypot(quad[3][0] - quad[0][0], quad[3][1] - quad[0][1]),
             np.hypot(quad[2][0] - quad[1][0], quad[2][1] - quad[1][1]))
    quad_aspect = qw / qh
    design_aspect = dw / dh
    if design_aspect >= quad_aspect:  # design wider -> pad top/bottom
        cw, ch = dw, round(dw / quad_aspect)
    else:                             # design taller -> pad left/right
        cw, ch = round(dh * quad_aspect), dh
    scale = min(max(design_scale, 0.3), 1.6)
    if scale < 1.0:
        cw, ch = round(cw / scale), round(ch / scale)
    elif scale > 1.0:
        # Enlarging: cap so the design still fits within the canvas.
        cw = max(dw, round(cw / scale))
        ch = max(dh, round(ch / scale))
    canvas = np.zeros((ch, cw, 4), dtype=np.uint8)
    x0, y0 = (cw - dw) // 2, (ch - dh) // 2
    canvas[y0:y0 + dh, x0:x0 + dw] = design_rgba
    return canvas


def _shading_map(base_rgba: np.ndarray, quad_mask: np.ndarray, strength: float) -> np.ndarray:
    """Per-pixel multiplier from the base's luminance, mean-normalized inside
    the print region. strength=0 -> flat paste (the gate's retry path)."""
    gray = cv2.cvtColor(base_rgba[:, :, :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
    region = gray[quad_mask > 0]
    mean = float(region.mean()) if region.size else 255.0
    shade = gray / max(mean, 1.0)
    return 1.0 + strength * (shade - 1.0)


def composite(design_rgba: np.ndarray, base_rgba: np.ndarray,
              quad: list[tuple[float, float]], shading_strength: float = 0.85,
              design_scale: float = 1.0) -> CompositeResult:
    canvas = _letterbox(design_rgba, quad, design_scale)
    ch, cw = canvas.shape[:2]
    bh, bw = base_rgba.shape[:2]

    src = np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]])
    dst = np.float32(quad)  # TL, TR, BR, BL
    m = cv2.getPerspectiveTransform(src, dst)

    warped = cv2.warpPerspective(  # the single design resample
        canvas, m, (bw, bh), flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    warped_rgb = warped[:, :, :3].astype(np.float32)
    alpha = warped[:, :, 3].astype(np.float32) / 255.0

    quad_mask = np.zeros((bh, bw), dtype=np.uint8)
    cv2.fillConvexPoly(quad_mask, dst.astype(np.int32), 255)

    shade = _shading_map(base_rgba, quad_mask, shading_strength)
    lit = np.clip(warped_rgb * shade[:, :, None], 0, 255)

    out = base_rgba.copy().astype(np.float32)
    a3 = alpha[:, :, None]
    out[:, :, :3] = lit * a3 + out[:, :, :3] * (1.0 - a3)

    return CompositeResult(image=out.astype(np.uint8), forward_m=m,
                           canvas=canvas, warped_alpha=alpha)

"""Base-image upscaling. Catalog bases are 1000–1200px but output must be
≥1500². The base is upscaled BEFORE compositing so the design is resampled
exactly once (upscaling a composited design a second time blurs it and costs
integrity score). The print quad is scaled by the same factor."""

from __future__ import annotations

import cv2
import numpy as np

MIN_OUTPUT_SIDE = 1500


def upscale_base(base_rgba: np.ndarray, quad: list[tuple[float, float]]
                 ) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Returns (upscaled base ≥1500 on its short side, quad in new coords)."""
    h, w = base_rgba.shape[:2]
    factor = max(1.0, MIN_OUTPUT_SIDE / min(w, h))
    if factor == 1.0:
        return base_rgba, list(quad)
    new_size = (round(w * factor), round(h * factor))
    up = cv2.resize(base_rgba, new_size, interpolation=cv2.INTER_CUBIC)
    return up, [(x * factor, y * factor) for x, y in quad]

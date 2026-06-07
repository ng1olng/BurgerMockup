"""Remove the "Hi, I am a placeholder" ink from catalog base images.

The BurgerPrints bases ship with a placeholder graphic on the garment;
composited designs with transparency would show it through, and its strokes
corrupt the shading map. Ink = saturated color or near-black pixels on the
garment (the opaque alpha region — fabric is desaturated and bright, so
wrinkles and drawstrings survive). Inpainted once, offline; the store serves
*_clean.png.

Run: python -m server.pipeline.clean_base
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from server.catalog.store import BASES_DIR, load_catalog
from server.pipeline.placement import garment_mask

# LIMITATION: these thresholds assume a LIGHT garment (current catalog bases
# are all white). On a dark/vivid garment the whole garment sits below
# _VAL_MAX and would be inpainted into mush — a dark-garment catalog needs a
# per-color ink model before this script may touch it.
_SAT_MIN = 50    # colored shapes
_VAL_MAX = 140   # near-black text
_DILATE_PX = 5
_INPAINT_RADIUS = 4


def clean(base_rgba: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(base_rgba, cv2.COLOR_RGBA2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    on_garment = garment_mask(base_rgba)
    ink = ((hsv[:, :, 1] > _SAT_MIN) | (hsv[:, :, 2] < _VAL_MAX)) & on_garment
    ink_mask = cv2.dilate(ink.astype(np.uint8) * 255,
                          np.ones((_DILATE_PX, _DILATE_PX), np.uint8))

    cleaned_bgr = cv2.inpaint(bgr, ink_mask, _INPAINT_RADIUS, cv2.INPAINT_TELEA)
    out = base_rgba.copy()
    out[:, :, :3] = cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2RGB)
    return out


def main() -> None:
    from PIL import Image

    for product in load_catalog():
        src = os.path.join(BASES_DIR, f"{product.short_code.upper()}.png")
        if not os.path.exists(src):
            continue
        base = np.array(Image.open(src).convert("RGBA"))
        cleaned = clean(base)
        dst = os.path.join(BASES_DIR, f"{product.short_code.upper()}_clean.png")
        Image.fromarray(cleaned).save(dst)
        print(f"cleaned {product.short_code} -> {dst}")


if __name__ == "__main__":
    main()

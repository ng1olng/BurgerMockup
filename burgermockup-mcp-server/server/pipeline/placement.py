"""Compute the design print quad from the base image — no annotation files.

The BurgerPrints public API exposes no print-area coordinates, so the print
region is derived at call time: the garment silhouette comes from the base
PNG's alpha channel, a proportional safe zone per garment type bounds the
printable region, and a placement keyword anchors the design box inside that
zone. The quad is inside the garment bbox by construction — a design can
never be composited outside the garment.
"""

from __future__ import annotations

import numpy as np

# Alpha threshold for the garment mask. Catalog bases carry "ghost" pixels —
# dark RGB hidden under near-zero alpha (matting remnants) — which must not
# inflate the garment bbox, so the mask requires solidly opaque pixels.
_ALPHA_MIN = 128

# Safe print zone per garment type as fractions of the garment bbox
# (x0, x1, y0, y1). Tuned against the catalog reference bases; the hoodie
# zone stops above the pouch pocket, tank bodies are narrower than tees.
_SAFE_ZONES = {
    "tshirt": (0.28, 0.72, 0.22, 0.75),
    "hoodie": (0.28, 0.72, 0.25, 0.58),
    "sweatshirt": (0.28, 0.72, 0.22, 0.72),
    "tank": (0.32, 0.68, 0.22, 0.75),
}
_DEFAULT_TYPE = "tshirt"

# full-front widens the envelope beyond the per-type safe zone while staying
# well inside the garment bbox (sleeves/hems excluded).
_FULL_FRONT_ZONE = (0.18, 0.82, 0.18, 0.80)

# Placement vocabulary accepted at the tool boundary (validated there, so a
# prompt-injected free-text placement can never reach the geometry).
PLACEMENTS = frozenset({
    "center", "chest", "left-chest", "right-chest", "top", "bottom", "full-front",
})

# Variety ladder for flat batches: fixed (placement, design_scale) sequence,
# ordered by visual-variety priority. The flat path is otherwise deterministic
# (same placement -> same quad -> identical image), so a batch walks this
# ladder to make each variant visibly different at zero render cost. Length 8
# matches the variant cap; scales stay inside the compositor clamp (0.3-1.6).
_LADDER: list[tuple[str, float]] = [
    ("center", 1.0), ("chest", 1.0), ("full-front", 1.0),
    ("center", 0.8), ("center", 1.25), ("top", 1.0),
    ("bottom", 1.0), ("left-chest", 1.0),
]


def placement_ladder(placement: str, n: int) -> list[tuple[str, float]]:
    """n distinct (placement, design_scale) combos; [0] is the exact request.

    Pure and deterministic: the same (placement, n) always yields the same
    list, so a later refine of any variant reproduces its own quad. Variants
    2..n walk `_LADDER` with the requested combo filtered out.
    """
    combos = [(placement, 1.0)]
    combos += [c for c in _LADDER if c != (placement, 1.0)]
    return combos[:n]


def garment_mask(base_rgba: np.ndarray, alpha_min: int = _ALPHA_MIN) -> np.ndarray:
    """Boolean mask of opaque garment pixels; raises on missing/empty alpha."""
    if base_rgba.ndim != 3 or base_rgba.shape[2] < 4:
        raise ValueError("base image has no alpha channel")
    mask = base_rgba[:, :, 3] > alpha_min
    if not mask.any():
        raise ValueError("base image alpha mask is empty")
    return mask


def garment_bbox(base_rgba: np.ndarray,
                 alpha_min: int = _ALPHA_MIN) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of opaque garment pixels."""
    ys, xs = np.nonzero(garment_mask(base_rgba, alpha_min))
    return float(xs.min()), float(ys.min()), float(xs.max()) + 1.0, float(ys.max()) + 1.0


def _fraction_box(box: tuple[float, float, float, float],
                  fx0: float, fx1: float, fy0: float, fy1: float,
                  ) -> tuple[float, float, float, float]:
    """Sub-box of `box` addressed by width/height fractions."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    return (x0 + fx0 * w, y0 + fy0 * h, x0 + fx1 * w, y0 + fy1 * h)


def compute_quad(base_rgba: np.ndarray, garment_type: str = _DEFAULT_TYPE,
                 placement: str = "center") -> list[tuple[float, float]]:
    """Print quad [(x,y) TL, TR, BR, BL] in base-image pixel coordinates.

    Unknown garment types fall back to t-shirt ratios; invalid placement
    raises ValueError (callers map it to a structured tool error).
    """
    if placement not in PLACEMENTS:
        raise ValueError(f"placement must be one of {sorted(PLACEMENTS)}")

    gbox = garment_bbox(base_rgba)
    zone_fracs = (_FULL_FRONT_ZONE if placement == "full-front"
                  else _SAFE_ZONES.get(garment_type, _SAFE_ZONES[_DEFAULT_TYPE]))
    zx0, zx1, zy0, zy1 = zone_fracs
    zone = _fraction_box(gbox, zx0, zx1, zy0, zy1)

    # Anchor the design box inside the safe zone. Chest boxes use the wearer's
    # frame: the wearer's LEFT chest is on the VIEWER's right of the image.
    anchors = {
        "center": (0.0, 1.0, 0.0, 1.0),
        "full-front": (0.0, 1.0, 0.0, 1.0),
        "chest": (0.0, 1.0, 0.0, 0.45),
        "left-chest": (0.65, 1.0, 0.0, 0.35),
        "right-chest": (0.0, 0.35, 0.0, 0.35),
        "top": (0.0, 1.0, 0.0, 0.5),
        "bottom": (0.0, 1.0, 0.5, 1.0),
    }
    ax0, ax1, ay0, ay1 = anchors[placement]
    bx0, by0, bx1, by1 = _fraction_box(zone, ax0, ax1, ay0, ay1)
    return [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]

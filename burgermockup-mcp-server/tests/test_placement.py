"""Placement engine: quads computed from base-image alpha, never annotated.

Pins: every placement stays inside the garment bbox; `center` overlaps the
retired hand-annotated quads (reasonableness, not pixel equality); ghost
pixels (dark RGB under near-zero alpha) cannot inflate the garment bbox.
"""

import numpy as np
import pytest
from PIL import Image

from server.pipeline.placement import (
    PLACEMENTS,
    compute_quad,
    garment_bbox,
    placement_ladder,
)

# Retired hand-annotated front quads, kept as reasonableness references only.
_HISTORICAL = {
    "USG5000": ("tshirt", (406.0, 294.0, 794.0, 878.0)),
    "USG18500": ("hoodie", (448.0, 308.0, 750.0, 764.0)),
}


def _base(code: str) -> np.ndarray:
    return np.array(
        Image.open(f"server/catalog/data/bases/{code}.png").convert("RGBA"))


def _rect(quad) -> tuple[float, float, float, float]:
    (x0, y0), _, (x1, y1), _ = quad
    return x0, y0, x1, y1


def _iou(a, b) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area = lambda r: (r[2] - r[0]) * (r[3] - r[1])  # noqa: E731
    return inter / (area(a) + area(b) - inter)


@pytest.mark.parametrize("code", list(_HISTORICAL))
@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
def test_every_placement_stays_inside_garment_bbox(code, placement):
    rgba = _base(code)
    gtype = _HISTORICAL[code][0]
    gx0, gy0, gx1, gy1 = garment_bbox(rgba)
    x0, y0, x1, y1 = _rect(compute_quad(rgba, gtype, placement))
    assert gx0 < x0 < x1 < gx1
    assert gy0 < y0 < y1 < gy1


@pytest.mark.parametrize("code", list(_HISTORICAL))
def test_center_overlaps_historical_hand_quad(code):
    gtype, hist = _HISTORICAL[code]
    rect = _rect(compute_quad(_base(code), gtype, "center"))
    assert _iou(rect, hist) > 0.3


def test_quad_corner_order_is_tl_tr_br_bl():
    quad = compute_quad(_base("USG5000"), "tshirt", "center")
    (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = quad
    assert tlx == blx < trx == brx
    assert tly == try_ < bry == bly


def test_ghost_pixels_do_not_inflate_garment_bbox():
    # Garment block + dark pixels under near-zero alpha in a far corner: the
    # bbox must come from opaque pixels only.
    rgba = np.zeros((100, 100, 4), dtype=np.uint8)
    rgba[20:80, 30:70] = (255, 255, 255, 255)
    rgba[0:5, 90:100] = (40, 40, 40, 2)  # ghost ink, alpha ~0
    assert garment_bbox(rgba) == (30.0, 20.0, 70.0, 80.0)


def test_unknown_garment_type_falls_back_to_tshirt():
    rgba = _base("USG5000")
    assert compute_quad(rgba, "cape", "center") == compute_quad(
        rgba, "tshirt", "center")


def test_invalid_placement_raises():
    with pytest.raises(ValueError):
        compute_quad(_base("USG5000"), "tshirt", "shoulder")


def test_missing_or_empty_alpha_raises():
    with pytest.raises(ValueError):
        garment_bbox(np.zeros((10, 10, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        garment_bbox(np.zeros((10, 10, 4), dtype=np.uint8))


def test_left_chest_sits_on_viewers_right():
    # Wearer's left chest = viewer's right half of the image.
    rgba = _base("USG5000")
    gx0, _, gx1, _ = garment_bbox(rgba)
    mid = (gx0 + gx1) / 2
    lx0, _, lx1, _ = _rect(compute_quad(rgba, "tshirt", "left-chest"))
    rx0, _, rx1, _ = _rect(compute_quad(rgba, "tshirt", "right-chest"))
    assert (lx0 + lx1) / 2 > mid > (rx0 + rx1) / 2


def test_deterministic():
    rgba = _base("USG18500")
    assert compute_quad(rgba, "hoodie", "chest") == compute_quad(
        rgba, "hoodie", "chest")


# --- placement_ladder: flat-batch variety combos --------------------------
# Pins: [0] is always the exact request; combos are unique; placements stay
# inside the tool vocabulary; scales stay inside the compositor clamp; the
# ladder is deterministic (refines must reproduce a variant's own quad).


@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
def test_ladder_n1_is_exact_request(placement):
    assert placement_ladder(placement, 1) == [(placement, 1.0)]


@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
def test_ladder_full_batch_unique_and_valid(placement):
    combos = placement_ladder(placement, 8)
    assert len(combos) == 8
    assert len(set(combos)) == 8
    assert combos[0] == (placement, 1.0)
    for p, s in combos:
        assert p in PLACEMENTS
        assert 0.3 <= s <= 1.6


def test_ladder_deterministic():
    assert placement_ladder("center", 5) == placement_ladder("center", 5)
    assert placement_ladder("chest", 3) == placement_ladder("chest", 3)

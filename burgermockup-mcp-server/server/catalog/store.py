"""Catalog store: crawled catalog.json + VN/EN fuzzy product matching for the
match_product tool.

The public BurgerPrints API exposes no print-area data; print regions are
computed from the base image at render time (server/pipeline/placement). The
garment type drives that placement's ratio table and is derived here from the
product NAME, because the API has no type field either.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from server.contracts import Color, Product

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CATALOG_JSON = os.path.join(DATA_DIR, "catalog.json")
BASES_DIR = os.path.join(DATA_DIR, "bases")

# VN/EN garment vocabulary -> catalog token. Matching is intentionally simple:
# the LLM has already normalized intent; this resolves naming, not semantics.
_GARMENT_WORDS = {
    "áo thun": "t-shirt", "ao thun": "t-shirt", "tee": "t-shirt", "tshirt": "t-shirt",
    "t-shirt": "t-shirt", "áo phông": "t-shirt",
    "hoodie": "hoodie", "áo nỉ có mũ": "hoodie",
    "tank": "tank", "ba lỗ": "tank", "tank top": "tank",
    "sweatshirt": "sweatshirt", "sweater": "sweatshirt", "crewneck": "sweatshirt",
    "áo nỉ": "sweatshirt",
}

# Ordered: specific garments before the t-shirt catch-all so "Crewneck
# Sweatshirt" never resolves as tshirt.
_NAME_TYPE_HINTS = (
    ("hoodie", "hoodie"),
    ("sweatshirt", "sweatshirt"),
    ("crewneck", "sweatshirt"),
    ("tank", "tank"),
)


def _derive_type(name: str) -> str:
    """Garment type from the product name (the API exposes no type field)."""
    lowered = name.lower()
    for hint, gtype in _NAME_TYPE_HINTS:
        if hint in lowered:
            return gtype
    return "tshirt"


def _to_product(d: dict) -> Product:
    return Product(
        short_code=d["short_code"],
        name=d["name"],
        type=_derive_type(d["name"]),
        available_colors=[Color(**c) for c in d.get("available_colors", [])],
        base_url=d.get("base_url", ""),
        resolution_default=d.get("resolution_default", ""),
    )


def load_catalog(path: str = CATALOG_JSON) -> list[Product]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [_to_product(d) for d in json.load(f)]


def get_product(product_id: str) -> Optional[Product]:
    for p in load_catalog():
        if p.short_code.lower() == product_id.lower():
            return p
    return None


def base_image_path(product_id: str) -> Optional[str]:
    # Prefer the inpainted base (placeholder ink removed) — the raw base shows
    # the placeholder through transparent design regions.
    for suffix in ("_clean", ""):
        path = os.path.join(BASES_DIR, f"{product_id.upper()}{suffix}.png")
        if os.path.exists(path):
            return path
    return None


def match(query: str, limit: int = 5) -> list[tuple[Product, float]]:
    """Score products against a free-text VN/EN mention."""
    q = query.lower()
    garment_hint = next((v for k, v in _GARMENT_WORDS.items() if k in q), None)
    scored: list[tuple[Product, float]] = []
    for p in load_catalog():
        score = 0.0
        name = p.name.lower()
        if p.short_code.lower() in q:
            score += 1.0
        if garment_hint and garment_hint in name:
            score += 0.8
        score += 0.1 * sum(1 for tok in q.split() if len(tok) > 2 and tok in name)
        if score > 0:
            scored.append((p, round(score, 2)))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]

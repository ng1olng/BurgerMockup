"""Catalog store: crawled catalog.json + annotated quads.json overlay +
VN/EN fuzzy product matching for the match_product tool.

quads.json exists because the public API exposes NO print-area coordinates —
quads were derived from the placeholder graphic on the base images and are the
required input for the compositor. A product without an annotated quad cannot
be composited (tools return a structured error rather than guessing).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from server.contracts import Color, Point, PrintArea, Product

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CATALOG_JSON = os.path.join(DATA_DIR, "catalog.json")
QUADS_JSON = os.path.join(DATA_DIR, "quads.json")
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


def _quads() -> dict:
    if not os.path.exists(QUADS_JSON):
        return {}
    with open(QUADS_JSON) as f:
        return json.load(f)


def _to_product(d: dict, quads: dict) -> Product:
    code_quads = quads.get(d["short_code"], {})
    return Product(
        short_code=d["short_code"],
        name=d["name"],
        type=d.get("type", "tshirt"),
        available_colors=[Color(**c) for c in d.get("available_colors", [])],
        print_areas=[
            PrintArea(
                name=a["name"],
                quad=[Point(x=p[0], y=p[1]) for p in code_quads.get(a["name"], [])],
                mesh=a.get("mesh"),
                source="annotated" if a["name"] in code_quads else "api",
            )
            for a in d.get("print_areas", [])
        ],
        base_url=d.get("base_url", ""),
        resolution_default=d.get("resolution_default", ""),
    )


def load_catalog(path: str = CATALOG_JSON) -> list[Product]:
    if not os.path.exists(path):
        return []
    quads = _quads()
    with open(path) as f:
        return [_to_product(d, quads) for d in json.load(f)]


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

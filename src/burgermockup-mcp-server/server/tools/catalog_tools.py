"""match_product tool — fuzzy VN/EN match against the cached BurgerPrints
catalog. The user never picks from a dropdown; the agent resolves mentions
like "áo thun trắng" conversationally via this tool."""

from __future__ import annotations

from server.catalog import store
from server.contracts import tool_error


def match_product(query: str) -> dict:
    """Match a natural-language product mention (VN or EN) against the catalog.
    Returns top candidates with scores; empty list means nothing matched."""
    query = (query or "").strip()
    if not query:
        return tool_error("empty_query", "query must not be empty")
    candidates = [
        {
            "product_id": p.short_code,
            "name": p.name,
            "type": p.type,
            "colors": [c.name for c in p.available_colors][:8],
            "score": score,
            "composable": any(a.quad for a in p.print_areas),
        }
        for p, score in store.match(query)
    ]
    return {"candidates": candidates}

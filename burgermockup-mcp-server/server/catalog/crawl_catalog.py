"""
Offline crawler: builds the catalog from the real BurgerPrints API. Reads
BP_API_KEY from env (NEVER hardcode). Fetches per-product detail (colors,
resolution, print_area names) for the demo set, filtering to planar garments.

Run: BP_API_KEY=... python -m server.catalog.crawl_catalog
Output: server/catalog/data/catalog.json
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

API_BASE = "https://api.burgerprints.com/v2"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CATALOG_JSON = os.path.join(DATA_DIR, "catalog.json")

# Prefix filters: keep planar garments, drop AOP/accessory/footwear.
_AOP_PREFIXES = ("AP", "EUAP", "ACC", "AMB", "SHAF", "FWL")
DEMO_CODES = ["USG5000", "USG2200", "USG18500", "USG18000"]

# BurgerPrints' WAF rejects the default Python urllib User-Agent (403); a
# browser-like UA is required.
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _get(path: str, api_key: str) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"api-key": api_key, "User-Agent": _USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def is_planar(short_code: str) -> bool:
    return not any(short_code.upper().startswith(p) for p in _AOP_PREFIXES)


def build_product(detail: dict) -> dict:
    data = detail["data"]
    return {
        "short_code": data["short_code"],
        "name": data["name"],
        "type": "tshirt",
        "available_colors": [
            {"id": c["id"], "name": c["name"], "color_hex": c.get("color_hex", "#ffffff")}
            for c in data.get("available_colors", [])
        ],
        "print_areas": [
            {"name": area, "quad": [], "mesh": None, "source": "api"}
            for area in (data.get("print_area") or ["front"])
        ],
        "base_url": data.get("url", ""),
        "resolution_default": data.get("resolution_default", ""),
    }


def crawl(api_key: str, codes: list[str] | None = None) -> list[dict]:
    codes = codes or DEMO_CODES
    products = []
    for code in codes:
        if not is_planar(code):
            print(f"skip non-planar {code}", file=sys.stderr)
            continue
        try:
            detail = _get(f"/product/{code}", api_key)
            products.append(build_product(detail))
            print(f"fetched {code}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 — best-effort crawl
            print(f"FAILED {code}: {e}", file=sys.stderr)
    return products


def main():
    api_key = os.getenv("BP_API_KEY")
    if not api_key:
        print("BP_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    os.makedirs(DATA_DIR, exist_ok=True)
    products = crawl(api_key)
    with open(CATALOG_JSON, "w") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print(f"wrote {len(products)} products -> {CATALOG_JSON}")


if __name__ == "__main__":
    main()

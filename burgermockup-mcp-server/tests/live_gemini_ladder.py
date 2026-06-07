"""Staged LIVE verification of the billed-Gemini lifestyle path. Run AFTER
putting a billed GEMINI_API_KEY in .env (and restarting nothing — this script
loads .env itself; the MCP server only needs a restart for the chat path).

Ladder (each step gates the next; total cost ≈ $0.04):
  1. key present + client constructs
  2. one real scene generation (~$0.039) — proves billing/quota
  3. composite a design onto the generated scene and save the mockup
     (inspect the file: does the edited scene keep the print region usable?)

Usage: .venv/bin/python tests/live_gemini_ladder.py [design.png]
Not a pytest module on purpose — it spends real money.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))  # runnable as a script: `python tests/live_gemini_ladder.py`
load_dotenv(_ROOT / ".env")


async def main() -> None:
    from server.catalog.store import base_image_path
    from server.pipeline import scene_gen
    from server.pipeline.lifestyle_render import render_lifestyle

    # -- step 1: configuration
    if not scene_gen.available():
        print("STEP 1 FAIL: GEMINI_API_KEY not set in burgermockup-mcp-server/.env")
        sys.exit(1)
    print(f"STEP 1 OK: key present, model {scene_gen.MODEL}")

    design = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / "Desktop" / "cat-design.png")
    if not Path(design).exists():
        print(f"STEP 1 FAIL: design not found: {design}")
        sys.exit(1)

    import numpy as np
    from PIL import Image

    from server.pipeline.placement import compute_quad
    quad = compute_quad(
        np.array(Image.open(base_image_path("USG5000")).convert("RGBA")),
        "tshirt", "center")

    # -- steps 2+3 in one call: render_lifestyle generates the scene (cost),
    # caches it by scene_id, and composites — exactly the chat path.
    spec = {"niche": "christmas"}
    try:
        result = await render_lifestyle(
            design, base_image_path("USG5000"), quad, spec,
            scene_id="ladder-christmas-1", garment_type="tshirt",
            prompt_label="ladder", mockup_id="ladder-1")
    except scene_gen.SceneGenError as e:
        print(f"STEP 2 FAIL (scene generation): {e}")
        print("  → free-tier quota or auth problem; check billing on the key")
        sys.exit(1)

    print(f"STEP 2 OK: scene generated (cost ${result['cost_usd']})")
    print(f"STEP 3 OK: mockup composited and saved")
    print(f"  mockup file_id: {result['file_id']}")
    print("  → inspect the file: the print region must look usable")
    print("LADDER PASS — restart the MCP server, then run a chat turn with "
          "n=1 (e.g. 'tạo 1 mockup scene giáng sinh').")


if __name__ == "__main__":
    asyncio.run(main())

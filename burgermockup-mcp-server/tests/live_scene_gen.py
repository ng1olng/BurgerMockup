"""Quick live test: generate 3 Christmas scenes with real Gemini API.

Reads GEMINI_API_KEY from .env, uses the committed USG5000_clean.png base,
writes output PNGs to files/ and prints the paths.

Run from burgermockup-mcp-server/:
    python -m tests.live_scene_gen
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

load_dotenv(override=True)


async def main() -> None:
    from server.pipeline import scene_gen
    from server.pipeline.prompts import scene_prompt
    from server.pipeline.upscale import upscale_base
    from server.storage import file_store

    if not scene_gen.available():
        print("ERROR: GEMINI_API_KEY not set in .env — cannot run live scene gen")
        sys.exit(1)

    file_store.init("files")
    base_path = "server/catalog/data/bases/USG5000_clean.png"
    base = Image.open(base_path).convert("RGBA")

    import json
    import numpy as np
    quads = json.load(open("server/catalog/data/quads.json"))
    quad = [tuple(p) for p in quads["USG5000"]["front"]]
    up_arr, _ = upscale_base(np.array(base), quad)
    up_base = Image.fromarray(up_arr)

    specs = [
        {"niche": "christmas"},
        {"niche": "christmas-outdoor"},
        {"niche": "christmas-gifting"},
    ]

    for spec in specs:
        niche = spec["niche"]
        prompt = scene_prompt(spec)
        print(f"\n--- {niche} ---")
        print(f"Prompt: {prompt[:120]}...")
        print("Calling Gemini...")
        scene_img, cost = await scene_gen.generate_scene(prompt, up_base)
        file_id, path = file_store.save_image(scene_img.convert("RGB"))
        print(f"Saved: {path}  (cost=${cost:.3f})")


if __name__ == "__main__":
    asyncio.run(main())

"""Live end-to-end check of the ASSEMBLED server over real streamable HTTP:
health → tools/list → multipart upload → match_product → generate with live
progress → fetch a served file by UUID. Exit 0 = pass."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys

import httpx
from fastmcp import Client
from PIL import Image

BASE = "http://127.0.0.1:8100"


async def main() -> None:
    async with httpx.AsyncClient() as http:
        assert (await http.get(f"{BASE}/health")).json()["ok"] is True

        buf = io.BytesIO()
        Image.new("RGBA", (200, 80), (10, 60, 200, 255)).save(buf, "PNG")
        up = await http.post(f"{BASE}/designs",
                             files={"file": ("logo.png", buf.getvalue(), "image/png")})
        design_id = up.json()["design_id"]
        print("uploaded design:", design_id)

    events: list[dict] = []

    async def on_progress(progress, total, message):
        events.append(json.loads(message))
        print("  progress:", events[-1]["event"], events[-1].get("variant_id", "")[:8])

    async with Client(f"{BASE}/mcp") as client:
        match = await client.call_tool("match_product", {"query": "áo thun"})
        pid = match.data["candidates"][0]["product_id"]
        print("matched:", pid)
        res = await client.call_tool(
            "generate_mockups",
            {"job_id": "live-1", "design_id": design_id, "product_id": pid,
             "scene_specs": [{"niche": "cafe"}], "n": 2},
            progress_handler=on_progress)
        variants = res.data["variants"]
        assert len(variants) == 2 and all(v["status"] == "ready" for v in variants)
        ready = [e for e in events if e["event"] == "variant_ready"]
        assert len(ready) == 2 and all("url" in e for e in ready)

    async with httpx.AsyncClient() as http:
        img = await http.get(ready[0]["url"])
        assert img.status_code == 200 and img.headers["content-type"] == "image/png"
        bad = await http.get(f"{BASE}/files/..%2f..%2fserver%2fmain.py")
        assert bad.status_code == 404

    print(f"LIVE CHECK PASS: {len(ready)} variants streamed, file served by UUID, "
          f"traversal blocked")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print(f"LIVE CHECK FAIL: {e}")
        sys.exit(1)

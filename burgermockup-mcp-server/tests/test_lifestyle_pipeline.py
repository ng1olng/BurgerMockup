"""Lifestyle path must-haves (scene model MOCKED — no paid calls in tests):
cache hit makes zero model calls; ECC absorbs small scene drift; heavy
distortion is rejected by the gate; no key → graceful flat fallback; abort
stops the loop with no further model calls."""

from __future__ import annotations

import base64
import io
import json
import uuid

import numpy as np
import pytest
from fastmcp import Client
from PIL import Image, ImageDraw

from server.pipeline import lifestyle_render, metrics, scene_cache, scene_gen
from server.storage import file_store
from server.main import mcp

pytestmark = pytest.mark.asyncio

QUAD = [tuple(p) for p in
        json.load(open("server/catalog/data/quads.json"))["USG5000"]["front"]]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    file_store.init(str(tmp_path / "files"))
    monkeypatch.setattr(metrics, "METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    yield


def _logo_b64() -> str:
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 30, 260, 170], fill=(220, 60, 30, 255))
    d.rectangle([20, 20, 280, 180], outline=(20, 40, 160, 255), width=8)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


class FakeSceneGen:
    """Counts calls; returns the upscaled clean base shifted by `shift` px —
    simulating a pose-preserving edit with residual drift."""

    def __init__(self, shift=(8, 5)):
        self.calls = 0
        self.shift = shift

    async def __call__(self, prompt, base_rgba_img):
        self.calls += 1
        arr = np.array(base_rgba_img.convert("RGBA"))
        out = np.roll(arr, self.shift, axis=(0, 1))
        return Image.fromarray(out), 0.039


async def _gen(client, n=1, niche="cafe", job="lj"):
    reg = await client.call_tool(
        "register_design", {"image_base64": _logo_b64(), "filename": "logo.png"})
    res = await client.call_tool(
        "generate_mockups",
        {"job_id": job, "design_id": reg.data["design_id"], "product_id": "USG5000",
         "scene_specs": [{"niche": niche}], "n": n})
    return res.data["variants"]


async def test_lifestyle_with_small_drift_passes_ecc_gate(monkeypatch):
    fake = FakeSceneGen(shift=(8, 5))
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(lifestyle_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        variants = await _gen(client)
        assert variants[0]["status"] == "ready", variants
        assert variants[0]["ssim"] >= 0.87
        assert fake.calls == 1
        assert scene_cache.load_scene(variants[0]["scene_id"]) is not None


async def test_cached_scene_makes_zero_model_calls(monkeypatch):
    fake = FakeSceneGen(shift=(0, 0))
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(lifestyle_render.scene_gen, "generate_scene", fake)
    scene_id = str(uuid.uuid4())
    base = Image.open("server/catalog/data/bases/USG5000_clean.png").convert("RGBA")
    from server.pipeline.upscale import upscale_base
    up, up_quad = upscale_base(np.array(base), QUAD)
    scene_cache.save_scene(scene_id, Image.fromarray(up), garment_type="tshirt",
                           color="", quad=up_quad)
    async with Client(mcp) as client:
        reg = await client.call_tool(
            "register_design", {"image_base64": _logo_b64(), "filename": "l.png"})
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "rf", "design_id": reg.data["design_id"],
             "product_id": "USG5000",
             "variants": [{"variant_id": "v1", "scene_id": scene_id}],
             "delta": {"type": "design", "change": "smaller"}})
        out = res.data["variants"][0]
        assert out["status"] == "ready"
        assert out["scene_id"] == scene_id      # scene preserved
        assert fake.calls == 0                  # ZERO model calls on design delta
        rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
        assert rows[-1]["cost_usd"] == 0.0 and rows[-1]["model"] == "scene-cache"


async def test_corrupting_composite_rejected_on_lifestyle_path(monkeypatch):
    # The gate guards DESIGN fidelity (a weird background alone cannot fail it —
    # the design is placed by our own transform). Simulate a composite that
    # corrupts the design: every gate pass scores below the lifestyle
    # threshold → the variant must fail, nothing sub-threshold ships.
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(lifestyle_render.scene_gen, "generate_scene",
                        FakeSceneGen(shift=(0, 0)))
    monkeypatch.setattr(lifestyle_render, "score", lambda *a, **k: 0.52)
    async with Client(mcp) as client:
        variants = await _gen(client, job="ldist")
        assert variants[0]["status"] == "failed"  # gate refused; nothing shipped
        rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
        assert rows[-1]["ssim"] == 0.52  # fail row logged


async def test_design_refine_recomposite_is_deterministic(monkeypatch):
    """Same cached scene + same change → byte-identical mockups. This is the
    pixel-level guarantee behind 'a design refine never changes the scene'."""
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    scene_id = str(uuid.uuid4())
    base = Image.open("server/catalog/data/bases/USG5000_clean.png").convert("RGBA")
    from server.pipeline.upscale import upscale_base
    up, up_quad = upscale_base(np.array(base), QUAD)
    scene_cache.save_scene(scene_id, Image.fromarray(up), garment_type="tshirt",
                           color="", quad=up_quad)
    urls = []

    async def on_progress(p, t, m):
        e = json.loads(m)
        if e["event"] == "variant_ready":
            urls.append(e["url"])

    async with Client(mcp) as client:
        reg = await client.call_tool(
            "register_design", {"image_base64": _logo_b64(), "filename": "l.png"})
        for job in ("det1", "det2"):
            await client.call_tool(
                "refine_mockups",
                {"job_id": job, "design_id": reg.data["design_id"],
                 "product_id": "USG5000",
                 "variants": [{"variant_id": "v1", "scene_id": scene_id}],
                 "delta": {"type": "design", "change": "smaller"}},
                progress_handler=on_progress)
    a, b = (open(file_store.resolve(u.rsplit("/", 1)[-1]), "rb").read() for u in urls)
    assert a == b  # identical scene pixels + identical composite

    # delta.scale actually changes the printed size — and still passes the gate
    async with Client(mcp) as client:
        reg = await client.call_tool(
            "register_design", {"image_base64": _logo_b64(), "filename": "l.png"})
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "det3", "design_id": reg.data["design_id"],
             "product_id": "USG5000",
             "variants": [{"variant_id": "v1", "scene_id": scene_id}],
             "delta": {"type": "design", "change": "thu nhỏ", "scale": 0.7}},
            progress_handler=on_progress)
        assert res.data["variants"][0]["status"] == "ready"
    scaled = open(file_store.resolve(urls[-1].rsplit("/", 1)[-1]), "rb").read()
    assert scaled != a  # smaller print -> different pixels


async def test_no_key_degrades_to_flat(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: False)
    async with Client(mcp) as client:
        variants = await _gen(client, job="lflat")
        assert variants[0]["status"] == "ready"
        rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
        assert rows[-1]["model"] == "flat-cv" and rows[-1]["cost_usd"] == 0.0


async def test_abort_stops_lifestyle_batch(monkeypatch):
    import asyncio

    from server import jobs

    class SlowGen(FakeSceneGen):
        async def __call__(self, prompt, base_rgba_img):
            await asyncio.sleep(0.5)
            return await super().__call__(prompt, base_rgba_img)

    slow = SlowGen(shift=(0, 0))
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(lifestyle_render.scene_gen, "generate_scene", slow)

    async with Client(mcp) as client:
        reg = await client.call_tool(
            "register_design", {"image_base64": _logo_b64(), "filename": "l.png"})

        async def abort_soon():
            await asyncio.sleep(0.7)
            jobs.abort("labort")

        call = client.call_tool(
            "generate_mockups",
            {"job_id": "labort", "design_id": reg.data["design_id"],
             "product_id": "USG5000", "scene_specs": [{"niche": "cafe"}], "n": 6})
        res, _ = await __import__("asyncio").gather(call, abort_soon())
        assert len(res.data["variants"]) < 6
        assert slow.calls < 6  # remaining variants made no model calls

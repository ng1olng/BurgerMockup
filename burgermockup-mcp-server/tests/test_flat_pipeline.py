"""Flat pipeline must-have tests: golden composite passes the integrity gate
end-to-end through the tool; a corrupted composite is retried then rejected
(with metrics rows for pass AND fail); output meets the size floor."""

from __future__ import annotations

import base64
import io
import json
import os

import pytest
from fastmcp import Client
from PIL import Image, ImageDraw

from server.pipeline import flat_render, metrics
from server.storage import file_store
from server.main import mcp

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    file_store.init(str(tmp_path / "files"))
    monkeypatch.setattr(metrics, "METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    yield


def _logo_b64() -> str:
    """Detail-rich test design: text-like strokes + shapes on transparency
    (a solid square would pass SSIM trivially; this one has fine structure)."""
    im = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 390, 290], outline=(20, 40, 160, 255), width=6)
    d.ellipse([60, 60, 180, 180], fill=(230, 90, 30, 255))
    d.line([200, 40, 360, 260], fill=(20, 40, 160, 255), width=10)
    for y in range(200, 280, 14):  # fine parallel strokes ~ text band
        d.line([40, y, 200, y], fill=(10, 10, 10, 255), width=4)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _generate_one(client) -> tuple[dict, list[dict]]:
    reg = await client.call_tool(
        "register_design", {"image_base64": _logo_b64(), "filename": "logo.png"})
    events: list[dict] = []

    async def on_progress(progress, total, message):
        events.append(json.loads(message))

    res = await client.call_tool(
        "generate_mockups",
        {"job_id": "flat-1", "design_id": reg.data["design_id"],
         "product_id": "USG5000", "scene_specs": [], "n": 1},
        progress_handler=on_progress)
    return res.data["variants"][0], events


async def test_golden_flat_composite_passes_gate():
    async with Client(mcp) as client:
        variant, events = await _generate_one(client)
        assert variant["status"] == "ready"
        assert variant["ssim"] >= 0.93, f"internal margin not met: {variant['ssim']}"

        ready = [e for e in events if e["event"] == "variant_ready"][0]
        file_id = ready["url"].rsplit("/", 1)[-1]
        out = Image.open(file_store.resolve(file_id))
        assert min(out.size) >= 1500  # output size floor

        rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
        assert len(rows) == 1 and rows[0]["ssim"] >= 0.93 and rows[0]["cost_usd"] == 0.0


async def test_corrupted_composite_is_rejected_with_metrics(monkeypatch):
    # Force the gate to score every composite below threshold: simulates a
    # corrupting composite path. Both retry passes must fail -> variant_failed.
    monkeypatch.setattr(flat_render, "score", lambda *a, **k: 0.41)
    async with Client(mcp) as client:
        variant, events = await _generate_one(client)
        assert variant["status"] == "failed"
        failed = [e for e in events if e["event"] == "variant_failed"]
        assert failed and failed[0]["message"] == \
            "design integrity could not be preserved for this variant"
        rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
        assert rows and rows[-1]["ssim"] == 0.41  # fail row logged too


async def test_text_heavy_raises_threshold(monkeypatch, tmp_path):
    # A 0.94 composite passes the normal flat gate (0.93) but must FAIL the
    # text-heavy gate (0.95) — proves the stricter threshold actually engages.
    monkeypatch.setattr(flat_render, "score", lambda *a, **k: 0.94)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(logo)
    from server.catalog.store import base_image_path
    import json as _json
    quad = [tuple(p) for p in
            _json.load(open("server/catalog/data/quads.json"))["USG5000"]["front"]]
    ok = flat_render.render_flat(str(logo), base_image_path("USG5000"), quad,
                                 text_heavy=False)
    assert ok["ssim"] == 0.94
    with pytest.raises(flat_render.GateFailure):
        flat_render.render_flat(str(logo), base_image_path("USG5000"), quad,
                                text_heavy=True)


async def test_design_meta_persisted_and_threaded():
    async with Client(mcp) as client:
        reg = await client.call_tool(
            "register_design", {"image_base64": _logo_b64(), "filename": "logo.png"})
        meta = file_store.design_meta(reg.data["design_id"])
        assert meta is not None
        assert meta["text_heavy"] == reg.data["text_heavy"]  # one source of truth


async def test_background_stays_white_where_base_was_transparent():
    # Catalog bases hide dark RGB under near-zero alpha (matting remnants).
    # The render must flatten them over white — alpha-dropping conversions
    # exposed them as gray blotches around the garment.
    import numpy as np

    from server.catalog.store import base_image_path

    async with Client(mcp) as client:
        variant, events = await _generate_one(client)
        assert variant["status"] == "ready"
        ready = [e for e in events if e["event"] == "variant_ready"][0]
        out = np.asarray(
            Image.open(file_store.resolve(ready["url"].rsplit("/", 1)[-1])).convert("RGB"),
            dtype=np.float32)

        base = Image.open(base_image_path("USG5000")).convert("RGBA")
        alpha = np.asarray(
            base.split()[-1].resize((out.shape[1], out.shape[0]), Image.BILINEAR),
            dtype=np.float32) / 255.0
        luma = out.mean(axis=2)
        assert luma[alpha < 0.1].min() >= 240  # ghost pixels were luma 114-185


async def test_flat_render_is_deterministic_and_fast():
    async with Client(mcp) as client:
        v1, e1 = await _generate_one(client)
        v2, e2 = await _generate_one(client)
        assert v1["ssim"] == v2["ssim"]  # same input -> same score
        ready = [e for e in e1 if e["event"] == "variant_ready"][0]
        assert ready["latency_ms"] < 2000  # <2s/variant requirement
        assert os.path.exists(file_store.resolve(ready["url"].rsplit("/", 1)[-1]))

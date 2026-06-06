"""Tool-conformance suite. Runs against the assembled server over an in-process
fastmcp Client (transport-level behaviors — progress delivery, abort — were
proven over real HTTP by tests/spike_*.py on the pinned versions)."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re

import pytest
from fastmcp import Client
from PIL import Image

from server import jobs
from server.storage import file_store
from server.main import mcp

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _tmp_files_dir(tmp_path, monkeypatch):
    file_store.init(str(tmp_path))
    # Hermetic: a developer's ambient GEMINI_API_KEY must not flip these tests
    # onto the live lifestyle path — conformance asserts the flat behavior.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    yield


def _png_b64(size=(64, 64), mode="RGBA") -> str:
    buf = io.BytesIO()
    Image.new(mode, size, (255, 0, 0, 255) if mode == "RGBA" else (255, 0, 0)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _register(client) -> str:
    res = await client.call_tool(
        "register_design", {"image_base64": _png_b64(), "filename": "logo.png"}
    )
    assert "design_id" in res.data, res.data
    return res.data["design_id"]


async def test_tools_listed():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        assert names == {"register_design", "match_product", "generate_mockups",
                         "refine_mockups", "export_listing"}


async def test_register_rejects_svg_and_bad_b64():
    async with Client(mcp) as client:
        res = await client.call_tool(
            "register_design", {"image_base64": base64.b64encode(b"<svg/>").decode(),
                                "filename": "evil.svg"})
        assert res.data["error"]["code"] == "unsupported_format"
        res = await client.call_tool(
            "register_design", {"image_base64": "!!!", "filename": "a.png"})
        assert res.data["error"]["code"] == "invalid_encoding"


async def test_decompression_bomb_rejected():
    # Small on wire, huge decoded: 9000x9000 = 81MP > 40MP cap.
    buf = io.BytesIO()
    Image.new("1", (9000, 9000), 0).save(buf, "PNG", optimize=True)
    assert buf.tell() < 200_000  # proves the wire cap alone would not catch it
    async with Client(mcp) as client:
        res = await client.call_tool(
            "register_design",
            {"image_base64": base64.b64encode(buf.getvalue()).decode(), "filename": "bomb.png"})
        assert res.data["error"]["code"] == "image_too_large"


async def test_match_product_vn():
    async with Client(mcp) as client:
        res = await client.call_tool("match_product", {"query": "áo thun trắng"})
        cands = res.data["candidates"]
        assert cands and cands[0]["product_id"] == "USG5000"
        assert cands[0]["composable"] is True  # annotated quad present


async def test_generate_clamps_n_and_isolates_failures():
    events = []

    async def on_progress(progress, total, message):
        events.append(json.loads(message))

    async with Client(mcp) as client:
        design_id = await _register(client)
        res = await client.call_tool(
            "generate_mockups",
            {"job_id": "job-clamp", "design_id": design_id, "product_id": "USG5000",
             "scene_specs": [{"niche": "cafe"}, {"niche": "__fail__"}], "n": 9999},
            progress_handler=on_progress)
        variants = res.data["variants"]
        assert len(variants) == 8  # MAX_VARIANTS clamp, not 9999
        statuses = {v["status"] for v in variants}
        assert statuses == {"ready", "failed"}  # __fail__ spec isolated, batch survived
        # Ready variants carry a browser-fetchable url whose file_id resolves;
        # failed variants carry none. Suffix-only match: PUBLIC_FILES_BASE may
        # vary per environment.
        for v in variants:
            if v["status"] == "ready":
                m = re.search(r"/files/([0-9a-f-]{36})\.png$", v["url"])
                assert m, v["url"]
                assert file_store.resolve(m.group(1)) is not None
            else:
                assert v["url"] is None
        ready = [e for e in events if e["event"] == "variant_ready"]
        failed = [e for e in events if e["event"] == "variant_failed"]
        assert len(ready) + len(failed) == 8
        assert all(e["message"] == "variant generation failed" for e in failed)


async def test_generate_unknown_ids_structured_errors():
    async with Client(mcp) as client:
        design_id = await _register(client)
        res = await client.call_tool(
            "generate_mockups", {"job_id": "j", "design_id": "nope",
                                 "product_id": "USG5000", "scene_specs": [], "n": 1})
        assert res.data["error"]["code"] == "design_not_found"
        res = await client.call_tool(
            "generate_mockups", {"job_id": "j", "design_id": design_id,
                                 "product_id": "NOPE", "scene_specs": [], "n": 1})
        assert res.data["error"]["code"] == "product_not_found"
        # USG2200 has no annotated quad -> must refuse rather than guess
        res = await client.call_tool(
            "generate_mockups", {"job_id": "j", "design_id": design_id,
                                 "product_id": "USG2200", "scene_specs": [], "n": 1})
        assert res.data["error"]["code"] == "no_print_area"


async def test_abort_stops_batch():
    async with Client(mcp) as client:
        design_id = await _register(client)

        async def abort_soon():
            await asyncio.sleep(0.6)
            jobs.abort("job-abort")

        call = client.call_tool(
            "generate_mockups",
            {"job_id": "job-abort", "design_id": design_id, "product_id": "USG5000",
             "scene_specs": [{"niche": "cafe"}], "n": 8})
        res, _ = await asyncio.gather(call, abort_soon())
        assert len(res.data["variants"]) < 8


async def test_refine_ordinal_and_design_delta_keeps_scene():
    async with Client(mcp) as client:
        design_id = await _register(client)
        gen = await client.call_tool(
            "generate_mockups", {"job_id": "g", "design_id": design_id,
                                 "product_id": "USG5000", "scene_specs": [], "n": 3})
        variants = gen.data["variants"]
        ref = await client.call_tool(
            "refine_mockups",
            {"job_id": "r", "design_id": design_id, "product_id": "USG5000",
             "variants": variants,
             "delta": {"type": "design", "change": "smaller", "target_ordinal": 2}})
        out = ref.data["variants"]
        assert len(out) == 1
        assert out[0]["variant_id"] == variants[1]["variant_id"]
        assert out[0]["scene_id"] == variants[1]["scene_id"]  # design delta reuses scene
        bad = await client.call_tool(
            "refine_mockups",
            {"job_id": "r2", "design_id": design_id, "product_id": "USG5000",
             "variants": variants, "delta": {"type": "design", "target_ordinal": 9}})
        assert bad.data["error"]["code"] == "ordinal_out_of_range"


async def test_no_env_leakage_in_results():
    os.environ["FAKE_SECRET_FOR_TEST"] = "sk-super-secret-value"
    try:
        async with Client(mcp) as client:
            design_id = await _register(client)
            res = await client.call_tool(
                "generate_mockups", {"job_id": "j", "design_id": design_id,
                                     "product_id": "USG5000",
                                     "scene_specs": [{"niche": "__fail__"}], "n": 1})
            assert "sk-super-secret-value" not in json.dumps(res.data)
    finally:
        del os.environ["FAKE_SECRET_FOR_TEST"]


async def test_export_is_stub():
    async with Client(mcp) as client:
        res = await client.call_tool("export_listing", {"variant_ids": ["x"]})
        assert res.data["status"] == "not_implemented"


async def test_files_route_rejects_traversal():
    # Route-level guard is regex+index in file_store.resolve — test it directly.
    assert file_store.resolve("../../.env") is None
    assert file_store.resolve("..%2f..%2f.env") is None
    assert file_store.resolve("0" * 36) is None  # not a UUID shape

"""On-model path must-haves (scene model MOCKED — no paid calls in tests):
model_persona routes on-model; result carries design_fidelity="ai-rendered"
plus echoed setting/persona; no scene_cache writes; failure degrades to flat;
no key degrades to flat; refine of an echoed on-model variant re-runs
on-model; setting-only specs never trigger the on-model path."""

from __future__ import annotations

import base64
import io
import json

import pytest
from fastmcp import Client
from PIL import Image, ImageDraw

from server.pipeline import metrics, on_model_render, scene_cache, scene_gen
from server.pipeline.scene_gen import SceneGenError
from server.storage import file_store
from server.main import mcp

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    file_store.init(str(tmp_path / "files"))
    monkeypatch.setattr(metrics, "METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    yield


def _logo_b64() -> str:
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 30, 260, 170], fill=(220, 60, 30, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


class FakeOnModelGen:
    """Counts calls; records prompts; returns the input image unchanged —
    simulating a fidelity-preserving on-model edit."""

    def __init__(self):
        self.calls = 0
        self.prompts: list[str] = []

    async def __call__(self, prompt, composited_img):
        self.calls += 1
        self.prompts.append(prompt)
        return composited_img.convert("RGBA"), 0.039


async def _gen_on_model(client, spec, job="om"):
    reg = await client.call_tool(
        "register_design", {"image_base64": _logo_b64(), "filename": "logo.png"})
    res = await client.call_tool(
        "generate_mockups",
        {"job_id": job, "design_id": reg.data["design_id"], "product_id": "USG5000",
         "scene_specs": [spec], "n": 1})
    return reg.data["design_id"], res.data["variants"]


async def test_persona_routes_on_model_with_echo_and_no_cache(monkeypatch):
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        _, variants = await _gen_on_model(
            client, {"setting": "on a sunny beach",
                     "model_persona": "a young woman"})
    v = variants[0]
    assert v["status"] == "ready" and v["url"], v
    assert fake.calls == 1
    assert "a young woman" in fake.prompts[0]      # on_model_prompt used
    assert "IDENTICAL" in fake.prompts[0]
    assert v["design_fidelity"] == "ai-rendered"
    assert v["setting"] == "on a sunny beach"      # stateless echo
    assert v["model_persona"] == "a young woman"
    assert v["degraded"] is False
    assert scene_cache.load_scene(v["scene_id"]) is None  # no cache writes
    rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
    assert rows[-1]["cost_usd"] == 0.039


async def test_setting_only_never_routes_on_model(monkeypatch):
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    # Lifestyle path would call its own generate_scene; pin it to fail loudly
    # if reached is unnecessary — just assert the on-model mock saw nothing
    # and the result is exact.
    from server.pipeline import lifestyle_render

    async def lifestyle_fake(prompt, img):
        return img.convert("RGBA"), 0.039

    monkeypatch.setattr(lifestyle_render.scene_gen, "generate_scene",
                        lifestyle_fake)
    async with Client(mcp) as client:
        _, variants = await _gen_on_model(
            client, {"setting": "on a sunny beach"}, job="om-setting")
    v = variants[0]
    assert v["status"] == "ready"
    assert fake.calls == 0                          # on-model NOT used
    assert v["design_fidelity"] == "exact"
    assert v["setting"] is None and v["model_persona"] is None


async def test_on_model_failure_degrades_to_flat(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: True)

    async def boom(prompt, img):
        raise SceneGenError("scene generation failed")

    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", boom)
    async with Client(mcp) as client:
        _, variants = await _gen_on_model(
            client, {"model_persona": "a man"}, job="om-fail")
    v = variants[0]
    assert v["status"] == "ready"
    assert v["degraded"] is True
    assert v["design_fidelity"] == "exact"          # flat output is exact
    rows = [json.loads(l) for l in open(metrics.METRICS_PATH)]
    assert rows[-1]["model"] == "flat-cv" and rows[-1]["cost_usd"] == 0.0


async def test_no_key_degrades_persona_request_to_flat(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: False)
    async with Client(mcp) as client:
        _, variants = await _gen_on_model(
            client, {"model_persona": "a man"}, job="om-nokey")
    v = variants[0]
    assert v["status"] == "ready" and v["degraded"] is True
    assert v["design_fidelity"] == "exact"


async def test_refine_of_on_model_variant_reruns_on_model(monkeypatch):
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        design_id, variants = await _gen_on_model(
            client, {"setting": "on a beach", "model_persona": "a young woman"},
            job="om-r1")
        v = variants[0]
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "om-r2", "design_id": design_id, "product_id": "USG5000",
             "variants": [v], "delta": {"type": "design", "scale": 0.7}})
        out = res.data["variants"][0]
    assert out["status"] == "ready"
    assert fake.calls == 2                          # full re-run, no cache reuse
    assert out["design_fidelity"] == "ai-rendered"
    assert out["model_persona"] == "a young woman"  # persona survives refine
    assert out["setting"] == "on a beach"           # setting kept (design delta)
    assert out["scene_id"] != v["scene_id"]         # fresh scene_id, no cache
    assert "a young woman" in fake.prompts[1]


async def test_refine_scene_delta_persona_override_changes_model(monkeypatch):
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        design_id, variants = await _gen_on_model(
            client, {"setting": "Paris", "model_persona": "a young woman"},
            job="om-p1")
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "om-p2", "design_id": design_id, "product_id": "USG5000",
             "variants": [variants[0]],
             "delta": {"type": "scene", "model_persona": "a young man"}})
        out = res.data["variants"][0]
    assert out["status"] == "ready"
    assert out["model_persona"] == "a young man"    # delta override wins
    assert out["setting"] == "Paris"                # setting kept from echo
    assert out["design_fidelity"] == "ai-rendered"
    assert "a young man" in fake.prompts[1]
    assert "Paris" in fake.prompts[1]


async def test_refine_persona_override_survives_stripped_echo(monkeypatch):
    # Weak host models (e.g. gpt-4o-mini) drop the echoed setting/persona
    # fields; the delta-level overrides must still route on-model.
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        design_id, variants = await _gen_on_model(
            client, {"setting": "Paris", "model_persona": "a young woman"},
            job="om-e1")
        stripped = {"variant_id": variants[0]["variant_id"],
                    "scene_id": variants[0]["scene_id"],
                    "placement": "center", "design_scale": 1}
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "om-e2", "design_id": design_id, "product_id": "USG5000",
             "variants": [stripped],
             "delta": {"type": "scene", "setting": "Paris",
                       "model_persona": "a young man"}})
        out = res.data["variants"][0]
    assert out["status"] == "ready"
    assert out["design_fidelity"] == "ai-rendered"  # NOT a flat fallback
    assert out["model_persona"] == "a young man"
    assert out["setting"] == "Paris"
    assert fake.calls == 2


async def test_refine_bare_scene_delta_with_stripped_echo_is_rejected(monkeypatch):
    # The silent-flat bug: scene delta with no fields + variant stripped of
    # its echo used to render a scene-less flat image flagged as success.
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        design_id, variants = await _gen_on_model(
            client, {"setting": "Paris", "model_persona": "a young woman"},
            job="om-b1")
        stripped = {"variant_id": variants[0]["variant_id"],
                    "scene_id": variants[0]["scene_id"],
                    "placement": "center", "design_scale": 1}
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "om-b2", "design_id": design_id, "product_id": "USG5000",
             "variants": [stripped], "delta": {"type": "scene"}})
    assert res.data["error"]["code"] == "empty_scene_delta"
    assert fake.calls == 1                          # no second render happened


async def test_refine_scene_delta_replaces_setting(monkeypatch):
    fake = FakeOnModelGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(on_model_render.scene_gen, "generate_scene", fake)
    async with Client(mcp) as client:
        design_id, variants = await _gen_on_model(
            client, {"setting": "on a beach", "model_persona": "a young woman"},
            job="om-s1")
        res = await client.call_tool(
            "refine_mockups",
            {"job_id": "om-s2", "design_id": design_id, "product_id": "USG5000",
             "variants": [variants[0]],
             "delta": {"type": "scene", "change": "in a cozy café"}})
        out = res.data["variants"][0]
    assert out["status"] == "ready"
    assert out["setting"] == "in a cozy café"       # change text replaced setting
    assert "in a cozy café" in fake.prompts[1]
    assert "a young woman" in fake.prompts[1]       # persona still applied

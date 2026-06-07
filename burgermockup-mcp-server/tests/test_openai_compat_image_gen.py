"""Tests for the OpenAI-compatible image generation handler.

Tests hit handle_image_generations() directly — the HTTP route in main.py is a
one-line wrapper, so testing the function covers all logic without needing ASGI
transport setup."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from server.pipeline import scene_gen
from server.storage import file_store
from server.tools.image_gen_compat import handle_image_generations

pytestmark = pytest.mark.asyncio

_FAKE_IMAGE = Image.new("RGB", (64, 64), (200, 100, 50))


class FakeSceneGen:
    def __init__(self, fail: bool = False):
        self.calls = 0
        self.fail = fail

    async def __call__(self, prompt, base_rgba_img):
        self.calls += 1
        if self.fail:
            from server.pipeline.scene_gen import SceneGenError
            raise SceneGenError("scene generation timed out")
        return _FAKE_IMAGE.convert("RGBA"), 0.039


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    file_store.init(str(tmp_path / "files"))


async def test_url_response_returns_openai_shape(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(scene_gen, "generate_scene", FakeSceneGen())
    result, status = await handle_image_generations(
        {"prompt": "a cheerful woman in christmas scene", "n": 2})
    assert status == 200
    assert "created" in result
    assert len(result["data"]) == 2
    assert all("url" in item for item in result["data"])


async def test_b64_json_response_is_valid_png(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(scene_gen, "generate_scene", FakeSceneGen())
    result, status = await handle_image_generations(
        {"prompt": "holiday scene", "response_format": "b64_json"})
    assert status == 200
    b64 = result["data"][0]["b64_json"]
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    assert img.size == (64, 64)


async def test_missing_prompt_returns_400(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    result, status = await handle_image_generations({"n": 1})
    assert status == 400
    assert result["error"]["code"] == "invalid_prompt"


async def test_no_api_key_returns_503(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: False)
    result, status = await handle_image_generations({"prompt": "a scene"})
    assert status == 503
    assert result["error"]["code"] == "not_configured"


async def test_scene_gen_failure_returns_502(monkeypatch):
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(scene_gen, "generate_scene", FakeSceneGen(fail=True))
    result, status = await handle_image_generations({"prompt": "a scene"})
    assert status == 502
    assert result["error"]["code"] == "generation_failed"


async def test_n_capped_at_4(monkeypatch):
    fake = FakeSceneGen()
    monkeypatch.setattr(scene_gen, "available", lambda: True)
    monkeypatch.setattr(scene_gen, "generate_scene", fake)
    result, status = await handle_image_generations({"prompt": "a scene", "n": 99})
    assert status == 200
    assert fake.calls == 4
    assert len(result["data"]) == 4

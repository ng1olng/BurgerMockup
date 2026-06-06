"""Unit tests for the OWUI design-bridge filter (integrations/).

The filter executes inside the Open WebUI backend, not this server — these
tests cover the pure message-mutation helpers and the inlet's dedup/failure
behavior with the HTTP upload mocked out. aiohttp is an OWUI runtime dep, so
skip cleanly where the dev env lacks it.
"""

from __future__ import annotations

import base64

import pytest

pytest.importorskip("aiohttp")

from integrations import owui_design_bridge_filter as bridge

PNG_B64 = base64.b64encode(b"fake-png-bytes").decode()
DATA_URL = f"data:image/png;base64,{PNG_B64}"
REG = {"design_id": "d-1", "width": 200, "height": 80, "has_alpha": True}


@pytest.fixture(autouse=True)
def _clear_cache():
    bridge._registered.clear()
    yield
    bridge._registered.clear()


def _image_body(text="put this on a tshirt"):
    return {
        "messages": [
            {"role": "assistant", "content": "hi"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": DATA_URL}},
                ],
            },
        ]
    }


# --- pure helpers ------------------------------------------------------------

def test_decode_data_url_png_and_jpeg_ext_mapping():
    data, name = bridge._decode_data_url(DATA_URL)
    assert data == b"fake-png-bytes" and name == "design.png"
    _, name = bridge._decode_data_url(f"data:image/jpeg;base64,{PNG_B64}")
    assert name == "design.jpg"


def test_decode_data_url_rejects_svg_and_garbage():
    assert bridge._decode_data_url(f"data:image/svg+xml;base64,{PNG_B64}") is None
    assert bridge._decode_data_url("not a data url") is None
    assert bridge._decode_data_url("data:image/png;base64,@@@") is None


def test_inject_context_appends_to_text_item():
    msg = {"role": "user", "content": [{"type": "text", "text": "hello"}]}
    bridge._inject_context(msg, ["[design registered: design_id=d-1]"])
    assert "hello" in msg["content"][0]["text"]
    assert "design_id=d-1" in msg["content"][0]["text"]


def test_inject_context_creates_text_item_when_absent():
    msg = {"role": "user", "content": [{"type": "image_url", "image_url": {"url": DATA_URL}}]}
    bridge._inject_context(msg, ["line"])
    assert msg["content"][0] == {"type": "text", "text": "line"}


def test_inject_context_noop_without_lines_or_list_content():
    msg = {"role": "user", "content": "plain string"}
    bridge._inject_context(msg, ["line"])
    assert msg["content"] == "plain string"


def test_last_user_message_picks_last():
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"}]
    assert bridge._last_user_message(msgs)["content"] == "c"
    assert bridge._last_user_message([]) is None


# --- inlet -------------------------------------------------------------------

async def test_inlet_registers_and_injects(monkeypatch):
    calls = []

    async def fake_register(self, data, filename):
        calls.append((data, filename))
        return dict(REG)

    monkeypatch.setattr(bridge.Filter, "_register", fake_register)
    f = bridge.Filter()
    body = await f.inlet(_image_body())

    text = body["messages"][-1]["content"][0]["text"]
    assert "design_id=d-1" in text and "200x80" in text
    assert calls == [(b"fake-png-bytes", "design.png")]


async def test_inlet_dedups_same_image_across_calls(monkeypatch):
    calls = []

    async def fake_register(self, data, filename):
        calls.append(1)
        return dict(REG)

    monkeypatch.setattr(bridge.Filter, "_register", fake_register)
    f = bridge.Filter()
    await f.inlet(_image_body())
    body2 = await f.inlet(_image_body())  # regenerate / new turn, same image

    assert len(calls) == 1  # second call served from cache
    assert "design_id=d-1" in body2["messages"][-1]["content"][0]["text"]


async def test_inlet_upload_failure_leaves_body_unchanged(monkeypatch):
    async def fake_register(self, data, filename):
        raise RuntimeError("/designs 422: rejected")

    monkeypatch.setattr(bridge.Filter, "_register", fake_register)
    f = bridge.Filter()
    body = await f.inlet(_image_body(text="original"))

    assert body["messages"][-1]["content"][0]["text"] == "original"
    assert bridge._registered == {}


async def test_inlet_ignores_string_content_and_missing_user():
    f = bridge.Filter()
    body = {"messages": [{"role": "user", "content": "no images here"}]}
    assert await f.inlet(dict(body)) == body
    assert await f.inlet({"messages": [{"role": "assistant", "content": "x"}]}) is not None

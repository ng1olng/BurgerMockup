"""Unit tests for the input moderation gate — fake genai client, no live API."""

from __future__ import annotations

import pytest

from server.pipeline import content_gate

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _fresh_gate(monkeypatch):
    content_gate._cache.clear()
    monkeypatch.setattr(content_gate, "_api_key", lambda: "fake-key")
    yield
    content_gate._cache.clear()


def _install_fake_genai(monkeypatch, reply: str = "no", exc: Exception | None = None):
    """Patch google.genai.Client with a fake; returns the call counter."""
    calls = {"n": 0}

    class _Models:
        async def generate_content(self, model, contents):
            calls["n"] += 1
            if exc is not None:
                raise exc

            class _R:
                text = reply

            return _R()

    class _Aio:
        models = _Models()

    class _Client:
        def __init__(self, api_key):
            self.aio = _Aio()

    import google.genai as genai_mod
    monkeypatch.setattr(genai_mod, "Client", _Client)
    return calls


async def test_yes_reply_is_restricted(monkeypatch):
    _install_fake_genai(monkeypatch, reply="Yes")
    assert await content_gate.is_restricted(["Messi"]) is True


async def test_no_reply_passes(monkeypatch):
    _install_fake_genai(monkeypatch, reply="no")
    assert await content_gate.is_restricted(["a young man"]) is False


async def test_garbage_reply_fails_open(monkeypatch):
    _install_fake_genai(monkeypatch, reply="maybe, depends")
    assert await content_gate.is_restricted(["whatever"]) is False


async def test_exception_fails_open_and_is_not_cached(monkeypatch):
    calls = _install_fake_genai(monkeypatch, exc=RuntimeError("quota"))
    assert await content_gate.is_restricted(["Messi"]) is False
    # Failure verdicts are never cached: once the provider recovers the same
    # text must be re-checked, not pinned to the fail-open answer.
    calls2 = _install_fake_genai(monkeypatch, reply="yes")
    assert await content_gate.is_restricted(["Messi"]) is True
    assert calls["n"] == 1 and calls2["n"] == 1


async def test_empty_texts_skip_api(monkeypatch):
    calls = _install_fake_genai(monkeypatch, reply="yes")
    assert await content_gate.is_restricted([]) is False
    assert await content_gate.is_restricted(["", "   "]) is False
    assert calls["n"] == 0


async def test_verdict_cached_per_normalized_text(monkeypatch):
    calls = _install_fake_genai(monkeypatch, reply="yes")
    assert await content_gate.is_restricted(["Messi"]) is True
    assert await content_gate.is_restricted(["messi"]) is True  # case-folded hit
    assert calls["n"] == 1


async def test_missing_api_key_fails_open(monkeypatch):
    calls = _install_fake_genai(monkeypatch, reply="yes")
    monkeypatch.setattr(content_gate, "_api_key", lambda: None)
    assert await content_gate.is_restricted(["Messi"]) is False
    assert calls["n"] == 0

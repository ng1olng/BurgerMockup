"""Unit tests for the Bearer-token gate (server/auth_middleware.py).

Pure ASGI + stdlib only — no fastmcp/starlette/uvicorn needed, so this runs even
without the full server deps installed. Drives the middleware with a stub downstream
app and a minimal ASGI send-collector.
"""

from __future__ import annotations

import asyncio

import pytest

from server.auth_middleware import BearerGateMiddleware


class _StubApp:
    """Downstream ASGI app: records that it ran, emits a trivial 200."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _scope(path: str, auth: str | None = None):
    headers = []
    if auth is not None:
        headers.append((b"authorization", auth.encode("latin-1")))
    return {"type": "http", "path": path, "headers": headers}


async def _drive(scope):
    """Run the gate; return (downstream_called, status_sent)."""
    stub = _StubApp()
    gate = BearerGateMiddleware(stub)
    status = {"code": None}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            status["code"] = msg["status"]

    await gate(scope, receive, send)
    return stub.called, status["code"]


def _run(coro):
    return asyncio.run(coro)


def test_gate_disabled_when_token_unset(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    called, status = _run(_drive(_scope("/mcp")))
    assert called and status == 200  # passes through untouched


def test_gate_disabled_when_token_blank(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "   ")  # whitespace stripped -> empty
    called, status = _run(_drive(_scope("/mcp")))
    assert called and status == 200


def test_mcp_rejected_without_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    called, status = _run(_drive(_scope("/mcp")))
    assert not called and status == 401


def test_mcp_rejected_with_wrong_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    called, status = _run(_drive(_scope("/mcp", auth="Bearer nope")))
    assert not called and status == 401


def test_mcp_allowed_with_valid_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    called, status = _run(_drive(_scope("/mcp", auth="Bearer secret")))
    assert called and status == 200


def test_empty_bearer_rejected(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    called, status = _run(_drive(_scope("/mcp", auth="Bearer ")))
    assert not called and status == 401


def test_non_ascii_header_does_not_crash(monkeypatch):
    # bytes compare must not raise on non-ASCII — attacker can't force a 500
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    called, status = _run(_drive(_scope("/mcp", auth="Bearer ÿÿ")))  # high bytes, not ASCII
    assert not called and status == 401


@pytest.mark.parametrize("path", ["/health", "/files/abc-123", "/files/"])
def test_exempt_paths_never_gated(monkeypatch, path):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    called, status = _run(_drive(_scope(path)))  # no auth header
    assert called and status == 200


def test_non_http_scope_passes_through(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")

    async def go():
        stub = _StubApp()
        gate = BearerGateMiddleware(stub)
        seen = {"lifespan": False}

        async def receive():
            return {"type": "lifespan.startup"}

        async def send(msg):
            seen["lifespan"] = True

        await gate({"type": "lifespan"}, receive, send)
        return stub.called

    assert _run(go()) is True  # delegated, not gated

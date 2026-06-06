"""Bearer-token gate for the MCP server.

The server has no built-in auth; locally it is reachable only over loopback. On a
public host the /mcp transport must not be open to the internet, or anyone can drive
paid Gemini generation. This enforces `Authorization: Bearer $MCP_AUTH_TOKEN` on the
MCP + mutation routes when a token is configured.

Exempt (never gated):
  /health      platform probe sends no auth header
  /files/...   rendered by the user's browser; an <img> request cannot carry an auth
               header (file ids are UUID-keyed, so not enumerable)

When MCP_AUTH_TOKEN is unset/empty the gate is disabled — preserves the loopback/compose
dev setup unchanged.

Implemented as pure ASGI (not Starlette's BaseHTTPMiddleware): it only inspects request
scope headers and never wraps/buffers the response body, so the streamable-HTTP SSE
responses pass through untouched.
"""

from __future__ import annotations

import hmac
import os

# Prefix match: anything under these paths skips the token check.
_EXEMPT_PREFIXES = ("/health", "/files/")

_UNAUTHORIZED_BODY = (
    b'{"error":{"code":"unauthorized","message":"missing/invalid bearer token"}}'
)


class BearerGateMiddleware:
    """ASGI middleware enforcing a shared Bearer token on non-exempt HTTP routes."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        # Only guard HTTP; websocket/lifespan pass straight through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
        if token and not scope.get("path", "").startswith(_EXEMPT_PREFIXES):
            # Headers in ASGI scope are a list of (name, value) byte tuples, names lowercased.
            auth = b""
            for name, value in scope.get("headers") or ():
                if name == b"authorization":
                    auth = value
                    break
            # Compare raw bytes (not decoded str): constant-time, and a non-ASCII header
            # can't raise TypeError. This guards a paid endpoint on a public host, so the
            # threat model includes a remote attacker timing the secret byte-by-byte.
            if not hmac.compare_digest(auth, b"Bearer " + token.encode("utf-8")):
                await self._reject(send)
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_UNAUTHORIZED_BODY)).encode("ascii")),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})

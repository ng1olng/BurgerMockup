"""
title: BurgerMockup Design Bridge
author: burgermockup
version: 0.1.0
description: Uploads chat-attached design images to the BurgerMockup MCP server
  (POST /designs) and injects the returned design_id into the message so the
  model can call match_product / generate_mockups with it.
"""

# Open WebUI Filter function. Installed into OWUI as a DB-stored function —
# this repo copy is the versioned source of truth.
#
# Why this exists: the model can SEE an attached image but cannot emit its
# bytes, and OWUI never injects attached files into MCP tool params, so
# register_design(image_base64) is unreachable from chat. By the time inlet
# runs, OWUI has already normalized every attached image into a
# data:image/...;base64 URL on the last user message
# (convert_url_images_to_base64 runs before process_filter_functions inlet),
# so the bytes are right here in the payload.

from __future__ import annotations

import base64
import hashlib
import logging

import aiohttp
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_UPLOAD_TIMEOUT_S = 30

# sha256(image bytes) -> /designs response. Module-level on purpose: OWUI
# caches the loaded function module, so regenerates and follow-up turns reuse
# the same design_id instead of re-uploading. Cleared on restart — harmless,
# the image just gets registered again.
_registered: dict[str, dict] = {}

# data:image/<subtype> -> upload filename extension accepted by the server.
_EXT_BY_SUBTYPE = {"png": "png", "jpeg": "jpg", "jpg": "jpg", "webp": "webp"}


def _decode_data_url(url: str) -> tuple[bytes, str] | None:
    """data:image/...;base64,... -> (bytes, filename) or None if unusable."""
    try:
        header, b64 = url.split(",", 1)
        subtype = header.split("data:image/", 1)[1].split(";", 1)[0].lower()
        ext = _EXT_BY_SUBTYPE.get(subtype)
        if ext is None:  # svg etc. — server rejects these anyway
            return None
        return base64.b64decode(b64, validate=True), f"design.{ext}"
    except Exception:
        return None


def _context_line(reg: dict) -> str:
    return (
        f"[design registered: design_id={reg['design_id']} "
        f"{reg['width']}x{reg['height']} has_alpha={reg['has_alpha']} — "
        f"use this design_id with match_product / generate_mockups]"
    )


def _inject_context(message: dict, lines: list[str]) -> None:
    """Append design context to the text part of a content-list message."""
    content = message.get("content")
    if not isinstance(content, list) or not lines:
        return
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            item["text"] = (item.get("text") or "") + "\n\n" + "\n".join(lines)
            return
    content.insert(0, {"type": "text", "text": "\n".join(lines)})


def _last_user_message(messages: list) -> dict | None:
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get("role") == "user":
            return message
    return None


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="Filter execution order")
        mcp_base_url: str = Field(
            default="http://burgermockup-mcp:8100",
            description="BurgerMockup MCP server base URL reachable from the "
            "Open WebUI backend (bare-metal server: http://host.docker.internal:8100)",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def _register(self, data: bytes, filename: str) -> dict:
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type="application/octet-stream")
        url = self.valves.mcp_base_url.rstrip("/") + "/designs"
        timeout = aiohttp.ClientTimeout(total=_UPLOAD_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=form) as resp:
                payload = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"/designs {resp.status}: {payload}")
                return payload

    async def inlet(self, body: dict, __event_emitter__=None) -> dict:
        # Never break the chat: any failure leaves the body untouched for the
        # affected image and the model proceeds without a design_id.
        try:
            message = _last_user_message(body.get("messages"))
            if message is None or not isinstance(message.get("content"), list):
                return body

            lines: list[str] = []
            for item in message["content"]:
                if not isinstance(item, dict) or item.get("type") != "image_url":
                    continue
                url = item.get("image_url", {}).get("url", "")
                if not url.startswith("data:image/"):
                    continue
                decoded = _decode_data_url(url)
                if decoded is None:
                    continue
                data, filename = decoded

                digest = hashlib.sha256(data).hexdigest()
                reg = _registered.get(digest)
                if reg is None:
                    try:
                        reg = await self._register(data, filename)
                    except Exception as e:
                        log.warning(f"design-bridge upload failed: {e}")
                        if __event_emitter__:
                            await __event_emitter__(
                                {
                                    "type": "status",
                                    "data": {
                                        "description": "Design upload to BurgerMockup failed — continuing without design_id",
                                        "done": True,
                                    },
                                }
                            )
                        continue
                    if "design_id" not in reg:  # structured tool_error payload
                        log.warning(f"design-bridge rejected upload: {reg}")
                        continue
                    _registered[digest] = reg
                lines.append(_context_line(reg))

            _inject_context(message, lines)
        except Exception as e:
            log.exception(f"design-bridge inlet error: {e}")
        return body

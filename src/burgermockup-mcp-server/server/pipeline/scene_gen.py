"""Gemini image client for lifestyle scene generation (single provider).

Generates the BLANK scene (garment + background, no design) by editing the
cleaned catalog base — design pixels never pass through this model. Errors are
mapped to fixed strings: provider response bodies are never echoed (they would
flow into the LLM context and the browser)."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

_log = logging.getLogger(__name__)

# Re-read on every call (below) so swapping GEMINI_API_KEY in .env takes
# effect without a server restart; explicit path avoids CWD/frame-walk
# surprises, and a missing file (Docker, env-only deploys) is a silent no-op.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Live-probed 2026-06-06: the API accepts this GA id and resolves it to the
# preview model internally (the 429 quota error named ...-preview-image), so
# the id is valid; image generation requires a BILLED key (free tier limit 0).
MODEL = "gemini-2.5-flash-image"
_TIMEOUT_S = 90
# Flat-rate estimate per generated image for the metrics table; the API does
# not return cost.
_COST_PER_IMAGE_USD = 0.039


class SceneGenError(Exception):
    """message is a fixed string, safe to surface."""


def _api_key() -> str | None:
    # override=True: .env is the source of truth at call time — without it a
    # stale GEMINI_API_KEY exported in the launching shell (e.g. ~/.zshrc)
    # silently shadows a freshly edited .env until the next restart.
    load_dotenv(_ENV_FILE, override=True)
    return os.environ.get("GEMINI_API_KEY")


def available() -> bool:
    return bool(_api_key())


def _client():
    from google import genai
    return genai.Client(api_key=_api_key())


async def _call_once(prompt: str, base_png: bytes) -> bytes:
    from google.genai import types

    client = _client()
    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=base_png, mime_type="image/png"),
                prompt,
            ],
        ),
        timeout=_TIMEOUT_S,
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise SceneGenError("scene model returned no image")


async def generate_scene(prompt: str, base_rgba: Image.Image) -> tuple[Image.Image, float]:
    """Returns (scene image, cost_usd). One retry on failure; fixed-string
    errors only."""
    if not available():
        raise SceneGenError("scene generation is not configured")
    buf = io.BytesIO()
    base_rgba.convert("RGB").save(buf, "PNG")
    base_png = buf.getvalue()

    last_error = "scene generation failed"
    for attempt in (1, 2):
        try:
            t0 = time.time()
            _log.info("scene model call attempt %d (model=%s)", attempt, MODEL)
            data = await _call_once(prompt, base_png)
            _log.info("scene model done in %dms cost=$%.3f",
                      int((time.time() - t0) * 1000), _COST_PER_IMAGE_USD)
            return Image.open(io.BytesIO(data)).convert("RGBA"), _COST_PER_IMAGE_USD
        except asyncio.TimeoutError:
            last_error = "scene generation timed out"
            _log.warning("scene model attempt %d timed out", attempt)
        except SceneGenError as e:
            last_error = str(e)
            _log.warning("scene model attempt %d failed: %s", attempt, e)
        except Exception:
            last_error = "scene generation failed"
            # Provider errors are mapped to a fixed string for the client; the
            # real traceback (quota, auth, schema drift) is logged server-side.
            _log.exception("scene model attempt %d failed", attempt)
    raise SceneGenError(last_error)

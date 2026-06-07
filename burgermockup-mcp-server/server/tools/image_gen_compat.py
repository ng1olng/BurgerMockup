"""OpenAI-compatible image generation handler (Path A — pure Gemini pass-through).

Accepts the standard POST /v1/images/generations payload and returns the
standard response shape so Open WebUI (and any OpenAI-compatible client) can
use this server as a drop-in image backend without the mockup compositor or
SSIM gate. The prompt is passed verbatim to Gemini; callers are expected to
have already enriched it (e.g. via OWUI's IMAGE_PROMPT_GENERATION pipeline).

A blank white 512×512 canvas is used as the Gemini img2img base so the model
generates freely from the prompt rather than editing an existing product photo.
"""

from __future__ import annotations

import base64
import io
import logging
import time

from PIL import Image

from server.pipeline import scene_gen
from server.pipeline.scene_gen import SceneGenError
from server.storage import file_store

_log = logging.getLogger(__name__)

# Blank white base fed to Gemini's img2img endpoint when no product photo is
# supplied — effectively pure text-to-image from the model's perspective.
_BLANK_BASE = Image.new("RGBA", (512, 512), (255, 255, 255, 255))


async def handle_image_generations(body: dict) -> tuple[dict, int]:
    """Process an OpenAI-compatible image generation request.

    Returns (response_dict, http_status_code).
    """
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return {"error": {"code": "invalid_prompt", "message": "prompt is required"}}, 400

    if not scene_gen.available():
        return {"error": {"code": "not_configured",
                          "message": "scene generation is not configured — set GEMINI_API_KEY"}}, 503

    raw_n = body.get("n", 1)
    try:
        n = max(1, min(int(raw_n), 4))  # cap at 4 for this endpoint
    except (TypeError, ValueError):
        return {"error": {"code": "invalid_n", "message": "n must be an integer"}}, 400

    response_format = body.get("response_format", "url")
    _log.info("image_generations prompt=%r n=%d format=%s", prompt[:80], n, response_format)

    data = []
    for i in range(n):
        try:
            scene_img, cost = await scene_gen.generate_scene(prompt, _BLANK_BASE)
            rgb_img = scene_img.convert("RGB")
            if response_format == "b64_json":
                buf = io.BytesIO()
                rgb_img.save(buf, "PNG")
                data.append({"b64_json": base64.b64encode(buf.getvalue()).decode()})
            else:
                file_id, _ = file_store.save_image(rgb_img)
                data.append({"url": file_store.url_for(file_id)})
            _log.info("image_generations variant %d/%d ready cost=$%.3f", i + 1, n, cost)
        except SceneGenError as e:
            _log.warning("image_generations variant %d/%d failed: %s", i + 1, n, e)
            return {"error": {"code": "generation_failed", "message": str(e)}}, 502
        except Exception:
            _log.exception("image_generations variant %d/%d unexpected error", i + 1, n)
            return {"error": {"code": "internal_error",
                              "message": "image generation failed"}}, 500

    return {"created": int(time.time()), "data": data}, 200

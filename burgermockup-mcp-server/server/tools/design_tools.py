"""register_design tool. Accepts base64 only — URL fetching was removed
deliberately (an LLM-constructed URL is an SSRF primitive). The browser path
uploads multipart via POST /designs instead of inflating through base64."""

from __future__ import annotations

import base64

from server.contracts import tool_error
from server.storage import file_store


def register_design(image_base64: str, filename: str) -> dict:
    """Register a design image (PNG/JPG/WebP, ≤25MB). Returns a design_id used
    by generate_mockups. The design's pixels are kept 100% intact — they are
    never sent through an image-generation model."""
    try:
        data = base64.b64decode(image_base64, validate=True)
    except Exception:
        return tool_error("invalid_encoding", "image_base64 is not valid base64")
    try:
        asset = file_store.ingest_design(data, filename)
    except file_store.IngestError as e:
        return tool_error(e.code, str(e))
    return {
        "design_id": asset.design_id,
        "width": asset.width,
        "height": asset.height,
        "has_alpha": asset.has_alpha,
        "text_heavy": asset.text_heavy,
    }

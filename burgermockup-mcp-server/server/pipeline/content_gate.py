"""Input-side moderation gate for scene text (persona/setting/niche/mood).

The negative line in the scene prompts ("no celebrities, no brands") loses
when the caller-supplied persona NAMES a celebrity — the prompt then orders
the image model to draw that person. This gate classifies the INPUT text with
a cheap text model before any paid image generation; a hit rejects the whole
tool call for $0.

Fail-open by design: a classifier outage must not take mockup generation down
with it (the prompt-level negative constraint remains the backstop), matching
the pipeline-wide degrade-over-error-wall policy. Provider response bodies are
never echoed — they would flow into the LLM context and the browser."""

from __future__ import annotations

import asyncio
import logging

from server.pipeline.scene_gen import _api_key

_log = logging.getLogger(__name__)

# Text model, NOT the -image variant used by scene_gen: this is a yes/no text
# classification, image pricing/quota would be wasted on it.
_MODEL = "gemini-2.5-flash"
_TIMEOUT_S = 15

# Verdict cache keyed by normalized text — refine loops resend the same
# persona/setting repeatedly; only definite verdicts are cached (failures are
# not, so a transient outage doesn't pin a fail-open verdict forever).
_cache: dict[str, bool] = {}

_CLASSIFIER_PROMPT = (
    "You are a content gate for a product-mockup generator. Does the "
    "following scene description reference a SPECIFIC real or famous person "
    "(by name, nickname, or unmistakable description, in any language — e.g. "
    "'Messi', 'CR7', 'Sơn Tùng') or a real brand/trademark (e.g. 'Nike')? "
    "Generic descriptions like 'a young man' or 'a female athlete' are fine. "
    "Reply with exactly one word: yes or no.\n\nText: {text}"
)


async def is_restricted(texts: list[str]) -> bool:
    """True when the combined scene text names a real person or brand.

    Empty input short-circuits to False with no API call. Any classifier
    failure (missing key, quota, timeout, schema drift) logs a warning and
    returns False — fail-open, see module docstring."""
    joined = " | ".join(t.strip() for t in texts if t and t.strip())
    if not joined:
        return False
    key = joined.lower()
    if key in _cache:
        return _cache[key]
    api_key = _api_key()
    if not api_key:
        return False  # scene generation is unconfigured too; nothing to gate
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=_MODEL,
                contents=_CLASSIFIER_PROMPT.format(text=joined),
            ),
            timeout=_TIMEOUT_S,
        )
        verdict = (response.text or "").strip().lower().startswith("yes")
        _cache[key] = verdict
        return verdict
    except Exception:
        # Fail-open: full traceback stays server-side, generation proceeds
        # with the prompt-level negative constraints as the only guard.
        _log.warning("content gate check failed; failing open", exc_info=True)
        return False

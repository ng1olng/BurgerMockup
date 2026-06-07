---
name: conformance-env-hermeticity
description: MCP conformance tests must pin scene_gen.available to False; delenv of GEMINI_API_KEY is insufficient
metadata:
  type: project
---

In `tests/test_tool_conformance.py`, the hermetic fixture must `monkeypatch.setattr(scene_gen, "available", lambda: False)`, not just `monkeypatch.delenv("GEMINI_API_KEY")`.

**Why:** `scene_gen._api_key()` reloads `.env` with `override=True` on every call, resurrecting a developer's ambient key. delenv alone let the conformance suite make real paid Gemini calls (flipping flat-path assertions onto the live lifestyle path).

**How to apply:** When reviewing any test that asserts flat/degraded behavior, confirm scene availability is pinned at the function boundary, not just via env. The flat vs lifestyle branch is decided by `has_cached_scene or (wants_scene and scene_gen.available())` in mockup_tools._render_variant.

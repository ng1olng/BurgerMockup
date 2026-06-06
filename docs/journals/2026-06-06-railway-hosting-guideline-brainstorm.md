# Railway Hosting Guideline Brainstorm Session

**Date**: 2026-06-06 10:00–10:30
**Severity**: Low (planning/documentation)
**Component**: Deployment; docs/deployment-guide.md
**Status**: Resolved

## What Happened

Brainstorm session on hosting vendored open-webui (v0.9.6, `src/open-webui/`) on Railway. Starting context: `/docs init` had just created the full initial docs set (README + 6 docs files) this morning. User confirmed requirements: build from vendored source, SQLite + Railway volume persistence, defer LLM backend decision, deliver guideline only (no actual deployment).

## The Brutal Truth

This was a tight, focused session with clear constraints and minimal scope-creep. Felt productive — consensus on tradeoffs emerged quickly, no second-guessing. The real win was identifying the `WEBUI_SECRET_KEY` footgun: without it, sessions evaporate every redeploy because the key lands on ephemeral FS, not the volume. Easy to miss, catastrophic for UX.

## Technical Details

**Key findings (verified against code):**
- `backend/start.sh:33` honors Railway-injected `PORT` environment variable — no Dockerfile override needed.
- `WEBUI_SECRET_KEY` unset → generated key written to ephemeral FS → invalidates all sessions on redeploy. MUST set explicitly as env var.
- Volume mount at `/app/backend/data` covers SQLite, uploads, Chroma vector DB, and runtime-downloaded embedding model (~80 MB).
- SQLite + in-memory socket manager + Railway single-attach volume → single replica only.

## What We Tried

**Three approaches evaluated:**
1. Railway builds slim Dockerfile (`USE_SLIM=true`) — chosen. Simplest, ~1.5–2 GB image, acceptable 15–20 min builds.
2. Full (non-slim) image — rejected. ~5 GB image hits Railway Hobby limits; only gains one-time embedding download skip.
3. GH Actions → GHCR → Railway image deploy — deferred. Best caching, but extra complexity; YAGNI for mockup.

## Root Cause Analysis

The key technical debt emerging: we haven't actually run this deployment yet. The guideline is theoretically sound (verified against code), but first-boot carries risk: build timeout on Hobby plan, secrets misconfiguration, volume mount paths. Also, LLM backend is deferred — user hasn't decided between OpenAI-compatible API vs. external Ollama, so that wiring is documented as templates, not tested.

## Lessons Learned

- **Verify secrets handling early.** The `WEBUI_SECRET_KEY` on ephemeral FS would've been a nasty surprise at first redeploy if not caught now.
- **Document scale-up paths explicitly.** Approach C (CI images) is deferred but documented; future implementer knows the escape hatch without re-brainstorming.
- **Tight constraints breed clarity.** YAGNI (rejecting full image) and single-replica limits forced clean decisions. No wasted time on "what if we add Redis" — not in scope.

## Next Steps

1. **Actual deployment (optional):** `/ck:plan` session to execute guideline against real Railway, verify first-boot, session persistence, healthcheck.
2. **LLM backend wiring:** When user decides OpenAI vs. Ollama, inject `OPENAI_API_BASE_URL`/`OPENAI_API_KEY` or `OLLAMA_BASE_URL` env vars.
3. **Guideline refresh:** Railway UI evolves; doc written against 2026 dashboard layout — may need minor refresh in Q3/Q4.

## Artifact

**Delivered:** "Hosting on Railway" section (~110 lines) appended to `docs/deployment-guide.md` (now 641 lines total). Covers prerequisites, service creation, volume, env vars table, LLM options, networking, first boot, caveats, and scale-up path.

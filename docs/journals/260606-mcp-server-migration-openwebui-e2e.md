# MCP Server Migration to OpenWebUI — E2E Verification Complete

**Date**: 2026-06-06 20:00
**Severity**: Medium (migration complete, one drift incident caught and resolved)
**Component**: burgermockup-mcp-server, OpenWebUI v0.9.6 integration
**Status**: Resolved

## What Happened

Migrated `burgermockup-mcp-server` (Python 3.12 FastMCP, 5 tools, 22/22 pytest) from `/hack-burger` to `/BurgerMockup` repo root via clean rsync. Verified full E2E through OpenWebUI v0.9.6 docker compose. Live gpt-4o-mini chat produced valid mockups: match_product → generate_mockups (SSIM 0.9524) → refine_mockups (SSIM 0.9446, zero image-model calls). Guardrail probe confirmed server clamps n=9999 to exactly 8 variants. Code review passed, docs updated.

## The Brutal Truth

Two issues surfaced mid-verification, both resolvable but frustrating. First: OpenWebUI's `/api/chat/completions` endpoint executes tool calls ONLY in the chat-session flow (with history.messages + currentId + session_id). Bare POST without session context returns raw unexecuted tool_calls — wasted two hours debugging a "tool hang" that was actually the API design. Second: source repo drifted while we were mid-verification (concurrent session in `/hack-burger` added logging) — caught by fidelity diff, forced a re-sync and full re-run, but byte-determinism held (SSIM 0.9524 reproduced exactly). Recovery cost: ~45 minutes, but trust in the pipeline intact.

## Technical Details

- **MCP streamable HTTP**: native mcpo proxy worked on first try. Connection URL `http://host.docker.internal:8100/mcp` (vendored compose already had extra_hosts). 127.0.0.1-bound server reachable immediately; staged fallbacks unnecessary.
- **Tool execution flow**: POST /openai/config/update requires OPENAI_API_CONFIGS. Tools only execute in session context: create chat → POST /api/chat/completions with chat_id + assistant_id + session_id → poll GET /api/v1/chats/{id}. Tool server id format: `server:mcp:burgermockup`.
- **Drift detected**: `diff -r hack-burger/burgermockup-mcp-server vs BurgerMockup/` caught new logging lines. Response: snapshot verified tree → rsync --delete → pytest 22/22 → restart → E2E smoke.
- **Design integrity**: refine_mockups with delta.type=design, scale 0.8 → SSIM 0.9446, zero image-model calls ($0). Model self-corrected a missing scene_id after tool error.

## What We Tried

1. POST /api/chat/completions with stream=true (no session context) → tool_calls returned unexecuted, looked like a hang.
2. Explored vendored OpenWebUI code for a "silent executor" — realized tool execution is gated at middleware.py:2954, requires session context.
3. Implemented proper chat-session flow (create message graph, pass session_id) → tools executed correctly first try.
4. Drift during verification forced full re-sync (rsync --delete) and re-run all 22 pytest + E2E smoke.

## Root Cause Analysis

Two root causes: (1) OpenWebUI's API design couples tool execution to session context — not documented in UI or obvious from endpoint names. (2) Concurrent work in `/hack-burger` repo drifted the source tree mid-verification. Neither was a surprise given the complexity, but both cost time.

## Lessons Learned

- **Session context is non-negotiable for tool execution in OpenWebUI.** "Tool calls returned but not executed" should have immediately triggered "check if session_id is missing" — lost time assuming a server-side hang.
- **Fidelity checks (diff -r) catch drift early.** The concurrent logging additions would have silently corrupted byte-determinism if we hadn't verified SSIM reproduction post-resync.
- **Byte-determinism across refines is golden.** SSIM 0.9524 → 0.9446 on design scale 0.8 with zero image-model calls proves the pipeline is isolated and reproducible, even after a drift+resync cycle.

## Next Steps

Nothing blocking. Migration complete, E2E verified, docs updated. Code review passed, tests all green. No commits made (explicit user decision). Repo ready for integration or further hardening.

---

**Status:** DONE
**Summary:** MCP server migration to OpenWebUI verified E2E; learned OpenWebUI couples tool execution to session context and caught source-tree drift via fidelity check.

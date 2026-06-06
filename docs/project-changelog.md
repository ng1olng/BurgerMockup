# Project Changelog

## [2026-06-06] MCP Server Railway Hosting Configuration

### Added
- **MCP Server Railway artifacts** (phases 01–02 complete)
  - `src/burgermockup-mcp-server/server/auth_middleware.py` — pure-ASGI Bearer gate, constant-time HMAC compare, self-disables when `MCP_AUTH_TOKEN` unset, exempts `/health` + `/files/`
  - `src/burgermockup-mcp-server/railway.toml` — config-as-code (builder Dockerfile, healthcheck `/health`, restart ON_FAILURE)
  - Modified `src/burgermockup-mcp-server/server/main.py` — `mcp.http_app()` + middleware stack + PORT binding (Railway or fallback to MCP_PORT)
  - `requirements.txt` — explicit uvicorn>=0.30

### Verified
- Pure-ASGI middleware avoids buffering SSE responses (streamable HTTP intact)
- Server binds `$PORT` (Railway injected) or `$MCP_PORT` (local fallback) or 8100 (default)
- Gate: `/mcp` 401 without valid token; `/health` + `/files/{id}` always open (UUID-keyed, unguessable)
- Local compose unchanged (no token set → gate disabled)
- 11 auth middleware tests passing; real fastmcp 3.4.1 boot verified

### Next
- Phase 03: Railway CLI deploy both services, env config, domain wiring
- Phase 04: Smoke tests + deployment-guide update

---

## [2026-06-06] MCP Server Migration & OpenWebUI Integration

### Added
- **burgermockup-mcp-server** migrated to repo root (`./burgermockup-mcp-server/`)
  - 5 MCP tools: `match_product`, `generate_mockups`, `refine_mockups`, `register_design`, `export_listing` (stub)
  - SSIM gate enforced server-side (≥0.92 flat, ≥0.85 lifestyle)
  - Stateless tool design: host passes session context; scene cached per design
  - Design pixels bypass image model via CV warping + masking in design space
  - Pinned versions: `fastmcp==3.4.1`, `mcp==1.27.2` (never bump; see CLAUDE.md lesson #2)

### Verified
- **OpenWebUI v0.9.6 E2E integration** (verification report: `plans/reports/verification-260606-openwebui-mcp-e2e.md`)
  - Native MCP (streamable HTTP) path: `http://host.docker.internal:8100/mcp`
  - 5/5 tools discovered + schemazoned correctly
  - Chat: `match_product("white t-shirt")` → `generate_mockups(n=2)` → SSIM 0.9524 ✓
  - Refinement: design-scale delta reuse cached scene (0 image-model calls) ✓
  - Server-side clamp (n=9999 → 8 variants) enforced ✓
  - 22 pytest (pipeline + tools) passing
  - Deterministic across re-runs (SSIM 0.9524 reproduced exactly)

### Documentation
- README.md: added MCP server to repo structure + quick-start run command
- docs/codebase-summary.md: new BurgerMockup MCP Server section with tool inventory, constraints, OpenWebUI notes

### Notes
- No auth required (local 127.0.0.1 binding; job_id + variant caps for credit guardrails)
- Free-tier Gemini quota = 0; billed key required for lifestyle scenes (flat variants degrade to $0 without key)
- Stale processes squat ports 8000/8100/3000; run `lsof -i :8000 -i :8100 -i :3000` before testing

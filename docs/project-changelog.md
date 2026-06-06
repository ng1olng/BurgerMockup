# Project Changelog

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

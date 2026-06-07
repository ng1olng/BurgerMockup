# MCP .env ↔ Docker-Compose Silent Drift Brainstorm

**Date**: 2026-06-07 05:09
**Severity**: Medium (edits to `burgermockup-mcp-server/.env` silently fail to reach container; usability friction)
**Component**: burgermockup-mcp-server (.env, .dockerignore), src/open-webui/docker-compose.mcp.yaml
**Status**: Decision approved; implementation deferred to user

## What Happened

User discovered that changes to `burgermockup-mcp-server/.env` never propagate to the running `burgermockup-mcp` container—no amount of `docker compose up -d` restarts help. User initially believed it was a build-time issue ("won't get .env every time when build"). Brainstorm unpacked the two deliberate design roots: (1) `.env` is listed in `.dockerignore`, so it never copies into the image; (2) `docker-compose.mcp.yaml` intentionally omits `env_file:` because the server `.env` contains values that break cross-container networking (e.g., `MCP_BIND_HOST=127.0.0.1` unreachable from compose network). Only `GEMINI_API_KEY` leaked through via compose interpolation, creating silent drift between the two .env files.

## The Brutal Truth

This is a classic collision between a deliberate safety decision (don't slurp whole .env at compose time—it has unsafe defaults) and usability (dev edits .env, expects them to work). The frustration: no error message, no warning, just silent failure. User had to read `.dockerignore` and `docker-compose.mcp.yaml` to understand why. The root is sound—passing `MCP_BIND_HOST=127.0.0.1` into a container *does* break it—but the design choice wasn't communicated anywhere obvious.

## Technical Details

**Root causes (verified via file inspection):**
- `burgermockup-mcp-server/.dockerignore`: contains `.env`, preventing file from copying into image.
- `src/open-webui/docker-compose.mcp.yaml`: no `env_file:` directive. Compose only interpolates `GEMINI_API_KEY` from parent `.env`, leaving `MCP_BIND_HOST`, `FILES_DIR`, `METRICS_PATH`, `PUBLIC_FILES_BASE` unset in container (use Dockerfile ENV defaults, which are often stale or host-relative).

**Unsafe values in `burgermockup-mcp-server/.env`:**
- `MCP_BIND_HOST=127.0.0.1` → unreachable cross-container; must be 0.0.0.0.
- `FILES_DIR=files` (relative) → points to host `files/` on startup, dodges the `/data/files` volume mount.
- `METRICS_PATH=metrics.jsonl` (relative) → same issue.

## What We Tried

1. **Option A: `env_file:` + explicit `environment:` overrides** (approved). Add `env_file: ../../burgermockup-mcp-server/.env` to compose, then pin unsafe vars in `environment:` block. Compose precedence: `environment:` > `env_file` > Dockerfile ENV. Whole .env flows; safety pins override. Single edit to compose; no .env duplication.

2. **Option B: Split .env into container-safe / host-only** (rejected). Over-engineered; requires multiple env files and complex tooling to keep in sync. Increases cognitive load on dev (which .env do I edit for this var?).

3. **Option C: `--env-file` CLI flag** (rejected). Fragile; hijacks whole-project compose interpolation and breaks `GEMINI_API_KEY` interpolation from parent `.env`.

## Decision

Approved Approach A: Single edit to `src/open-webui/docker-compose.mcp.yaml`:
```yaml
services:
  burgermockup-mcp:
    env_file: ../../burgermockup-mcp-server/.env
    environment:
      MCP_BIND_HOST: "0.0.0.0"              # override unsafe default
      FILES_DIR: /data/files                # override unsafe relative path
      METRICS_PATH: /data/metrics.jsonl     # override unsafe relative path
      PUBLIC_FILES_BASE: /data/public       # override unsafe relative path
```

This preserves the safety rationale (unsafe vars overridden at compose time) while allowing the whole .env to flow. No .env duplication; no build-time changes; no fragile CLI flags.

User chose to implement directly (deferred from brainstorm).

## Root Cause Analysis

A prior safety decision ("don't env_file the whole .env, it has unsafe defaults") wasn't surfaced anywhere (no comment, no docs). When the deliberate constraint collided with usability ("why doesn't my .env edit work?"), the solution wasn't to reverse the safety decision, but to layer compose `environment:` overrides on top of `env_file:`. Compose's precedence semantics make this clean: env_file provides defaults, environment overrides them, Dockerfile ENV is fallback.

## Lessons Learned

- **Silent-failure defaults are usability debt.** No error message = developers blame their own understanding ("maybe I need to rebuild?") before reading implementation. Document why .env doesn't flow (even a 1-line comment in .dockerignore).
- **Safety decisions outlive their context.** A careful "don't pass whole .env" choice from months ago persists; when questioned now, no one remembers why. Rationale should live in code or compose comments, not just in brainstorm notes.
- **Compose precedence is your friend.** Rather than splitting configs or adding CLI flags, layer `environment:` overrides on top of `env_file:`. One compose file, one .env, explicit safety pins—all three can coexist cleanly.

## Next Steps

1. User to implement compose edit per Approach A.
2. Add inline comment to `.dockerignore` or compose explaining the safety pins.
3. Verify post-edit: `docker compose up -d`, edit `burgermockup-mcp-server/.env`, `docker compose up -d` again, confirm new values reach container.

---

**Status:** DONE
**Summary:** Diagnosed .env drift as intentional safety constraint (unsafe defaults in .env, `.dockerignore` prevents flow to image, compose omits `env_file`). Approved Approach A: add `env_file:` to compose with explicit `environment:` overrides for unsafe vars (MCP_BIND_HOST, FILES_DIR, METRICS_PATH, PUBLIC_FILES_BASE). Single-file solution; preserves safety; unblocks dev usability. Implementation deferred to user.

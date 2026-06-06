# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A wrapper repository vendoring **Open WebUI v0.9.6** (an AI chat platform) under `src/open-webui/` (~310K LOC), used as a base for mockups and customizations. All application code lives in `src/open-webui/`; this root only adds `docs/`, `plans/`, and `.claude/` tooling.

**Read `./README.md` and the relevant file in `./docs/` before planning or implementing** — `docs/codebase-summary.md`, `docs/system-architecture.md`, `docs/code-standards.md`, `docs/deployment-guide.md` already map the vendored codebase in detail.

## Commands

All commands run from `src/open-webui/`:

```bash
# Development (two processes)
npm install
npm run dev               # Frontend: Vite dev server on :5173 (fetches Pyodide first)
cd backend && ./dev.sh    # Backend: uvicorn --reload on :8080 (dev.sh default PORT=8080)

# Docker (single container, recommended for quick runs)
docker compose up -d      # Serves built app on :8080

# Lint / format
npm run lint              # ESLint + svelte-check + pylint backend/
npm run lint:frontend     # ESLint only (--fix)
npm run lint:types        # svelte-check (TypeScript)
npm run lint:backend      # pylint backend/
npm run format            # Prettier
npm run format:backend    # Ruff (Python)

# Tests
npm run test:frontend     # Vitest (passWithNoTests)
npx vitest run path/to/file.test.ts   # Single frontend test file
# Backend: pytest framework ready, no tests in base

# Build & type check
npm run build             # vite build (static SPA)
npm run check             # svelte-kit sync + svelte-check

# Health
curl http://localhost:8080/health
```

## Architecture

SPA (SvelteKit static adapter) + FastAPI backend. Frontend talks to backend via REST with Bearer tokens, SSE streaming for chat responses, and Socket.IO for real-time (presence, channels, CRDT note collaboration via Yjs/pycrdt).

### Backend — `src/open-webui/backend/open_webui/`

- `main.py` — FastAPI app assembly: middleware stack, router mounting, startup/shutdown
- `routers/` — 30 route modules (auths, chats, models, retrieval, knowledge, tools, channels, notes, ...)
- `models/` — 25 SQLAlchemy 2.0 entities (SQLite dev / PostgreSQL prod)
- `retrieval/` — RAG pipeline: `loaders/` (9 document types), `vector/` (15 vector DB backends), reranking
- `utils/` — cross-cutting logic; note `middleware.py` (~232KB, chat completion orchestration), `oauth.py`, `access_control.py`
- `socket/` — Socket.IO server + CRDT sync (Redis-backed when scaled)
- `config.py` — ~200 env-backed persistent settings (stored in DB, hot-reloadable); add new config here, not ad-hoc env reads
- `migrations/` — Alembic (46 migrations); schema changes require a new migration

### Frontend — `src/open-webui/src/`

- `routes/` — SvelteKit routes; `(app)/` is the auth-gated group (`c/[id]` chat, `admin/`, `workspace/`, `notes/`, `channels/`)
- `lib/components/` — ~530 Svelte 5 components organized by domain (`chat/`, `common/`, `admin/`, `icons/`, ...)
- `lib/apis/` — 30 fetch-based API modules mirroring backend routers (Bearer token pattern, EventSource for streaming)
- `lib/stores/` — 40+ Svelte writable stores (no Redux/Zustand); subscribe via `$store`
- `routes/+layout.svelte` — root bootstrap (Socket.IO connect, stores init, Pyodide worker)
- `lib/i18n/` — 63 locales; user-facing strings go through i18next (`npm run i18n:parse` to extract)

### Cross-cutting patterns

- Adding an API feature typically touches: backend `models/` (+ Alembic migration) → `routers/` → frontend `lib/apis/` → `lib/components/` / `routes/` — keep names aligned across layers
- Auth: JWT Bearer tokens issued by `routers/auths.py`; route guards via FastAPI dependencies in `utils/auth.py`; RBAC via groups + `utils/access_control.py`
- Chat completions flow through `utils/middleware.py` (model routing, tool calling, RAG injection) before hitting OpenAI/Ollama connectors

## Conventions

- Project rules live in `.claude/rules/` (workflows, development rules) — they are auto-loaded and authoritative
- Vendored upstream code: prefer minimal, surgical diffs in `src/open-webui/` to keep future upstream merges feasible
- Plans go in `./plans/`, documentation in `./docs/` — keep `docs/` updated after significant changes
- Python: Ruff formatting, snake_case; Frontend: Prettier (tabs), Svelte 5 syntax (runes/`$store`), TypeScript

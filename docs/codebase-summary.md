# Codebase Summary

## Overview

**Scale**: ~310K LOC vendored from Open WebUI v0.9.6
- **Backend**: 180K LOC (222 Python files) at `src/open-webui/backend/open_webui/`
- **Frontend**: 126K LOC (604 files) at `src/open-webui/src/`
- **Routes**: 5.3K LOC (55 route files)
- **Config**: 128K LOC in `config.py` (200+ persistent settings)

**Tech Stack**:
- Backend: FastAPI 0.135.1, SQLAlchemy 2.0 async, Redis, python-socketio 5.16.1, Alembic (46 migrations)
- Frontend: SvelteKit 2.5.27, Svelte 5.53.10, TypeScript 5.5.4, Tailwind CSS 4, Vite 5.4.21
- Database: SQLite (dev), PostgreSQL, async SQLAlchemy ORM
- Containers: Python 3.11-slim, Node 22-alpine

---

## BurgerMockup MCP Server (`burgermockup-mcp-server/`)

**Scale**: Python 3.12 FastMCP server with 5 stateless tools for design→mockup CV pipeline.

**Key Constraints**:
- Versions pinned: `fastmcp==3.4.1`, `mcp==1.27.2` (never bump; fastmcp #1305 breaks abort semantics)
- SSIM gate enforced server-side: ≥0.92 flat, ≥0.85 lifestyle (internal margin ≥0.93/0.87)
- Design pixels never pass through image model (warped + masked in design space, scored with CV)
- No auth required (local 127.0.0.1 only; job_id minting + variant caps provide credit guardrails)

**5 MCP Tools** (`server/tools/`):
1. **match_product** — Query BurgerPrints catalog by design description; return product + print-quad metadata
2. **generate_mockups** — Full pipeline: scene generation (Gemini), compositing, SSIM verification, retry on fail
3. **refine_mockups** — Design-only refine (scale, rotate) within a session; zero image-model calls; reuse cached scene
4. **register_design** — Persist design metadata (hash, print-area) for catalog indexing
5. **export_listing** — Stub for marketplace publish (TBD)

**Pipeline** (`server/cv/`):
- Scene caching per design (byte-deterministic; reused across refines)
- ECC-based quad detection + homography warping
- Design masking + SSIM scoring (gaussian window, design-on-unwarped-base reference)
- Per-variant error isolation + fast-fail

**OpenWebUI Integration**:
- Native MCP via streamable HTTP: `http://host.docker.internal:8100/mcp` from Docker
- Tool IDs: `server:mcp:burgermockup`
- No progress UI surfacing (MCP notifications ignored by OpenWebUI v0.9.6; final result only)
- Ready variants carry `url` field in final tool result; LLM renders as `![variant](url)` markdown in chat (bare-metal local; browser must reach `PUBLIC_FILES_BASE` + `/files/{id}.png`)

---

## Directory Map

### Backend (`src/open-webui/backend/open_webui/`)

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `routers/` | 30 FastAPI route handlers | `auths.py`, `chats.py`, `models.py`, `retrieval.py`, `tools.py`, `knowledge.py`, etc. |
| `models/` | 25 SQLAlchemy ORM entities | `auth.py`, `chat.py`, `user.py`, `knowledge.py`, `file.py`, `note.py` (CRDT), etc. |
| `retrieval/` | RAG pipeline | `loaders/` (9 doc types), `vector/` (15 backends), `reranking.py` |
| `utils/` | Core utilities | `middleware.py` (232KB), `tools.py` (MCP), `oauth.py` (90KB), `access_control.py`, `telemetry.py` |
| `socket/` | Real-time WebSocket | `main.py` (SocketIO + CRDT via pycrdt) |
| `config.py` | Settings (128KB) | 200+ env-backed persistent configs, hot-reload via Redis/DB |
| `main.py` | FastAPI app | Middleware setup, route mounting, startup/shutdown |
| `migrations/` | Alembic DB migrations | 46 SQL schema versions |

### Frontend (`src/open-webui/src/`)

| Directory | Purpose | Key Files / Stats |
|-----------|---------|-------------------|
| `lib/components/` | ~530 Svelte files in 23 domains | `chat/` (22), `common/` (44), `icons/` (178), `admin/`, `layout/`, `channel/`, `workspace/`, `calendar/`, etc. |
| `lib/apis/` | 30 fetch-based API modules | Bearer token pattern, EventSource streaming for chat |
| `lib/stores/` | 40+ Svelte writable stores | `config`, `user`, `chats`, `models`, `socket`, `theme`, `locale`, `ui`, etc. |
| `routes/` | 55 SvelteKit routes (5.3K LOC) | `(app)` (auth-gated group), `admin/`, `workspace/`, `c/[id]` (chat), `notes/`, `channels/`, `playground/`, `/auth/`, `+page.svelte` (root) |
| `lib/i18n/` | i18next configuration | 63 locales, lazy-loaded JSON |
| `lib/utils/` | Shared utilities | Date formatting, validation, parsing |
| `lib/workers/` | Web Workers | Pyodide 0.28.2 (Python-in-browser), Kokoro TTS |
| `+layout.svelte` | Root layout (1213 lines) | Socket.IO, Pyodide bootstrap, stores initialization |

### Key Dependencies

**Frontend** (package.json, ~80 dev + prod deps):
- UI: Svelte 5, SvelteKit 2, Tailwind CSS 4, Bits UI v2, DOMPurify
- Editors: Tiptap v3 (WYSIWYG), CodeMirror 6, Xterm 6
- Data: Chart.js, Vega, Mermaid 11
- Media: PDF.js, Transformers.js (NLP-in-browser), ONNX Runtime
- Real-time: Socket.IO client, Yjs (CRDT)
- Utils: i18next, date-fns, uuid, highlight.js

**Backend** (pyproject.toml, ~60 deps):
- FastAPI 0.135.1, Uvicorn, Pydantic
- ORM: SQLAlchemy 2.0 async, Alembic, aiosqlite, psycopg
- Auth: python-jose, cryptography, argon2, authlib, PyJWT
- Real-time: python-socketio 5.16.1, pycrdt
- HTTP: aiohttp, httpx, requests
- Cache: Redis, aiocache
- RAG: Vector DB clients (pinecone, qdrant, langchain-vectorstores, etc.)
- Search: Tavily, web crawlers
- Task scheduler: APScheduler
- Logging: loguru, OpenTelemetry

---

## Backend Routers (30 endpoints)

| Router | Models Touched | Key Endpoints |
|--------|----------------|---------------|
| `auths.py` | User, Auth | POST /auths/login, /register, /logout, /mfa, OAuth flows |
| `users.py` | User, UserModel | GET /users, POST /users, profile, role updates |
| `chats.py` | Chat, ChatMessage | GET/POST/PUT /chats/[id], new, tags, shared |
| `chat_messages.py` | ChatMessage | Messages by chat, edit, delete |
| `channels.py` | Channel | GET/POST /channels, subscribe, leave |
| `models.py` | Model | List models, pull, push, delete |
| `ollama.py` | — | Ollama backend integration (pull, generate) |
| `openai.py` | — | OpenAI API integration |
| `retrieval.py` | Document, Collection | RAG query, doc upload |
| `knowledge.py` | Knowledge | Knowledge base CRUD |
| `files.py` | File | Upload, download, chunk |
| `folders.py` | Folder | Organize knowledge |
| `functions.py` | Function | User-defined function tools |
| `tools.py` | Tool | MCP tools, custom tools |
| `skills.py` | Skill | Skill CRUD (automation) |
| `images.py` | — | Image generation, upload |
| `audio.py` | — | Speech (Whisper, TTS) |
| `memories.py` | Memory | Chat context memory |
| `notes.py` | Note | CRDT notes with collab editing |
| `prompts.py` | Prompt | Prompt templates |
| `pipelines.py` | Pipeline | Custom pipeline middleware |
| `evaluations.py` | Evaluation | Model benchmarks |
| `tasks.py` | Task | Background job management |
| `terminals.py` | Terminal | Xterm.js shell access |
| `automations.py` | Automation | Workflow triggers |
| `calendar.py` | CalendarEvent | Event scheduling |
| `analytics.py` | — | Usage metrics (read-only) |
| `groups.py` | Group | Org units, RBAC |
| `scim.py` | — | LDAP/SCIM provisioning |
| `configs.py` | Config | Global settings (auth tokens, etc.) |

---

## Frontend Components (Domain Organization)

| Domain | Count | Examples |
|--------|-------|----------|
| `chat/` | 22 | MessageInput, MessageAction, KnowledgeBase, CodeBlock, ModelSelector |
| `common/` | 44 | Modal, Button, Toggle, Dropdown, Sidebar, Navbar, Pagination |
| `icons/` | 178 | SVG icon components (all UI icons) |
| `admin/` | — | ModelManager, AuthConfig, UserManager |
| `layout/` | — | Header, Sidebar, AppBar |
| `channel/` | — | ChannelList, ChannelCreate, MemberInvite |
| `workspace/` | — | KnowledgePanel, PromptLibrary, ToolManager |
| `calendar/` | — | CalendarView, EventForm |
| `automations/` | — | WorkflowBuilder, TriggerConfig |
| `notes/` | — | NotesEditor (CRDT enabled), NotesPanel |
| `playground/` | — | RAGPlayground, ModelComparison |

---

## Frontend Stores (Svelte Reactive State)

Key writable stores in `lib/stores/index.ts`:
- `config` — Global settings (theme, language, AI settings)
- `user` — Current user profile
- `chats` — Chat list, active chat, message history
- `models` — Available models (local, cloud, ollama)
- `socket` — WebSocket connection state
- `theme` — Dark/light mode
- `locale` — Current language (i18next)
- `ui` — Sidebar visible, modal states
- `settings` — User preferences (auth backends, integrations)
- `web` — Web search config
- `memories` — Memory bank per chat
- `folders` — Knowledge folder hierarchy
- `groups` — User's groups/roles

---

## Frontend Routes (SvelteKit App Router)

| Route Group | Files | Purpose |
|-------------|-------|---------|
| `(app)/` | Auth-gated | Protected pages |
| `(app)/admin/[tab]` | Admin panel | Model, auth, knowledge, group management |
| `(app)/workspace/` | Workspace hub | Models, knowledge, prompts, tools, settings |
| `(app)/c/[id]` | Chat view | Chat page, message tree |
| `(app)/notes` | Notes | Collaborative notes |
| `(app)/channels` | Channels | Team channels |
| `(app)/playground` | Playground | RAG/model testing |
| `/auth/` | Public | Login, register, OAuth callback |
| `/s/[id]` | Public | Shared chat view |
| `/watch` | Public | Chat streaming (no auth) |
| `/` | Public | Root (redirects to `/auth` or `/`) |

---

## RAG Pipeline (Retrieval Subsystem)

### Document Loaders (`retrieval/loaders/`)
1. **marker** — PDF, HTML → markdown
2. **mineru** — Scientific papers, complex layouts
3. **mistral** — Mistral platform content
4. **tavily** — Web search results
5. **youtube** — Transcript extraction
6. **paddleocr** — OCR for scanned docs
7. **jira** — JIRA issue/ticket loader
8. **s3** — AWS S3 bucket crawl
9. **web** — Generic web crawler

### Vector DB Backends (`retrieval/vector/`)
1. PgVector (PostgreSQL native)
2. Milvus (vector-specific DB)
3. Pinecone (managed vector DB)
4. Qdrant (fast, scalable)
5. Chroma (embedded default)
6. Weaviate (knowledge graphs)
7. Elasticsearch (full-text + vectors)
8. OpenSearch (ES fork)
9. MariaDB (MySQL-compatible)
10. Oracle 23AI (enterprise)
11. OpenGauss (PostgreSQL fork)
12. S3Vector (S3-based index)
13. Valkey (Redis alternative)
14. SQLite (embedded)
15. Hybrid search (multi-backend)

### Reranking
- Cross-encoder models (default: none, optional: `jina-reranker`)
- Semantic re-scoring of retrieved docs

---

## Configuration (config.py)

128KB of persistent, hot-reloadable settings:
- **Auth**: OAuth/OIDC providers, JWT expiry, session timeout
- **Models**: Model registry, rate limits, routing rules
- **RAG**: Vector DB selection, embedding model, reranking
- **Integrations**: API keys (OpenAI, Anthropic, etc.), webhooks
- **UI**: Theme, language, branding
- **Security**: CORS origins, secret key, headers
- **Observability**: OTel endpoints, log levels
- **Advanced**: Cache TTL, job timeouts, max file size

Changes persist to DB and Redis; no restart needed (except secret key).

---

## Middleware Stack

| Middleware | Purpose |
|-----------|---------|
| Compression | Brotli/gzip response compression |
| Redirect | HTTPS redirect, trailing slash |
| Security Headers | X-Frame-Options, CSP, HSTS |
| CORS | Cross-origin request filtering |
| Auth Token | JWT/API key extraction, request signing |
| Session | StarSessions (Redis-backed) |
| WebSocket Guard | Upgrade protocol validation |
| Audit Logging | All API calls logged (user, model, tokens) |

---

## Database Models (25 entities)

Core entities (SQLAlchemy ORM):
- **User** — Authentication, roles, settings
- **Auth** — OAuth/LDAP/OIDC providers
- **Chat, ChatMessage** — Conversation history
- **Channel, ChannelMessage** — Team communication
- **Model** — Model registry
- **Knowledge, File, Folder** — RAG documents
- **Note** — CRDT-enabled collaborative notes
- **Memory** — Context memory
- **Tool, Skill, Function** — Custom tools
- **Automation, Task** — Workflow scheduling
- **CalendarEvent** — Event scheduling
- **Group** — RBAC groups
- **Prompt, PipelineConfig** — Templates & middleware
- **Feedback, Evaluation** — Model benchmarks
- **AccessGrant** — Fine-grained permissions
- **SharedChat** — Public/private chat links
- **PromptHistory** — Prompt version history
- **OAuthSession** — OAuth state management

---

## File Size Notes

- **Largest files**: `middleware.py` (232KB), `config.py` (128KB), `oauth.py` (90KB)
- **Largest components**: `+layout.svelte` (1213 lines), various chat UI components
- **Code organization**: Follows modular patterns (routers isolated, components domain-scoped, stores centralized)
- **Migration count**: 46 Alembic versions (schema evolution tracked)

---

## Unresolved Questions

- Test coverage baseline (no test suite discovered in vendored code)?
- Custom code extension points (only via routers/middleware, no plugin system)?
- Vector DB recommendation for production (Qdrant, Milvus, or self-hosted PgVector)?

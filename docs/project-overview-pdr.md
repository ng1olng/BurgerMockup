# Project Overview & PDR

## Project Statement

**Burger Print** is a minimal wrapper repository that vendors **Open WebUI v0.9.6** (~310K LOC) to serve as a **customization and mockup base** for enterprise AI chat deployments. It provides a stable, vendored snapshot of Open WebUI's full feature set: multi-model chat, RAG, tools/MCP, real-time collaboration, and extensive middleware/auth integrations.

The repo is **not a fork**—it's a clean vendoring at `src/open-webui/` with room for company-specific branding, deployment configs, and feature customizations in future phases.

---

## Scope: What Open WebUI Brings

### Core Chat & Models
- **Multi-model orchestration**: OpenAI, Anthropic, Azure, Ollama (local), Mistral, Bedrock, AWS SageMaker, HuggingFace Inference, Replicate, etc.
- **Model chaining**: Fallback chains, cost routing, rate-limit steering
- **Streaming**: Server-sent events (SSE) + WebSocket for real-time responses
- **Chat history**: Full message trees, branching, prompt history, memory management

### Retrieval-Augmented Generation (RAG)
- **9 document loaders**: Marker (PDF, HTML), MinEru (scientific docs), Mistral, Tavily web search, YouTube, PaddleOCR, Jira, S3, web crawler
- **15 vector DB backends**: PgVector, Milvus, Pinecone, Qdrant, Chroma, Weaviate, Elasticsearch, OpenSearch, MariaDB, Oracle 23AI, OpenGauss, S3Vector, Valkey, SQLite, Hybrid search
- **Cross-encoder reranking**: Semantic reranking of retrieved docs for relevance
- **Embedding models**: Pluggable sentence transformers (default: all-MiniLM-L6-v2)

### Tools & Function Calling
- **Model Context Protocol (MCP)**: stdio/SSE servers, bidirectional tool invocation
- **Custom function tools**: User-defined functions, library tools (code execution)
- **Skill automation**: Workflows, background tasks (APScheduler)

### Real-Time Collaboration
- **CRDT-based notes**: Conflict-free collaborative editing (pycrdt + Yjs)
- **WebSocket chat streaming**: Live typing, message reactions, user presence
- **Redis-distributed SocketIO**: Multi-server chat room support

### Channels & Workspaces
- **Channels**: Invite-based team communication, shared models/knowledge bases
- **Workspace**: Knowledge base library, prompt templates, model registry
- **Access control**: RBAC (role-based + attribute-based), OAuth/OIDC

### Media & Extensions
- **Image handling**: Generation (OpenAI, DALL-E), inline viewing, upload/storage
- **Audio/Speech**: Whisper transcription, Kokoro TTS (in-browser), Eleven Labs
- **Rendering**: Markdown with Mermaid diagrams, syntax-highlighted code, LaTeX, Tiptap WYSIWYG editor
- **Web workers**: Pyodide (Python-in-browser), ONNX Runtime, Transformers.js

### Observability
- **Audit logging**: All API calls logged with user/model/tokens
- **OpenTelemetry**: Distributed tracing (optional: Grafana LGTM stack)
- **Telemetry**: Usage analytics, model performance metrics
- **Health checks**: `/health` endpoint, dependency status

---

## Architecture Snapshot

```
SvelteKit SPA (Svelte 5)
    ↓ fetch + Bearer auth
FastAPI server (async)
    ↓ SQLAlchemy + Redis + Vector DBs
Database layer (SQLite, PostgreSQL, etc.)
```

**Backend (30 routers)**:
- `auths`, `users`, `chats`, `channels` — core entities
- `models`, `ollama`, `openai` — model integration
- `retrieval`, `knowledge`, `files`, `folders` — RAG pipeline
- `functions`, `tools`, `skills` — extensibility
- `notes` — CRDT collaboration
- `memories`, `prompts`, `pipelines` — context management
- `images`, `audio` — media processing
- `tasks`, `automations`, `calendar` — scheduling
- `analytics`, `evaluations`, `feedbacks` — observability
- `configs`, `groups`, `scim` — admin/LDAP

**Middleware stack**: Compression (brotli/gzip), CORS, auth (JWT/API key), session management, audit logging, WebSocket guard, security headers.

**Frontend (530+ components)**:
- Chat UI: message rendering, streaming, markdown, code blocks
- Admin panel: model/auth/knowledge management
- Workspace: channels, notes, knowledge bases
- Playground: RAG testing, model benchmarks
- Settings: profile, preferences, integrations

---

## Initial Goals

### Phase 0 (Completed)
- ✅ Clean vendor of Open WebUI v0.9.6
- ✅ Minimal repo structure (no custom code outside src/open-webui)
- ✅ Docker multi-stage build (Node 22 → Python 3.11-slim)
- ✅ docker-compose variants (base, gpu, api, data, otel)

### Phase 1+ (Placeholder — TBD)
- Branding/customization ("Burger" mockup assets)
- Deployment topology (prod infra, scaling)
- Feature work (custom auth flows, proprietary integrations)
- Security hardening (secrets, compliance)
- Performance tuning (caching, indexing)

---

## Key Assumptions

1. **Vendored = stable**: We snapshot Open WebUI at v0.9.6; updates are intentional, not continuous.
2. **Backend-first customization**: Python FastAPI is the extension point (routers, middleware, models).
3. **Frontend via Svelte**: SvelteKit (adapter-static) deployed as static SPA + FastAPI backend.
4. **Vector DBs are pluggable**: RAG works with any of 15+ backends; no hard lock-in.
5. **Docker-first deployment**: Dockerfile + compose variants handle most production scenarios.
6. **Self-hosted or cloud**: Works with local Ollama, cloud APIs, or hybrid setups.

---

## Success Criteria

- Open WebUI runs unmodified under `src/open-webui/` (vendoring preserved)
- Docker build + compose work out-of-box with sensible defaults
- Development workflow (npm dev + dev.sh) is smooth and reproducible
- Documentation is accurate and links are not stale
- Custom code (if added in future phases) follows established conventions (FastAPI routers, Svelte components, kebab-case files)

---

## Unresolved Questions

- Specific mockup/branding direction ("Burger" → visual assets, color scheme, logo placement)?
- Custom authentication flow (OAuth/OIDC passthrough, MFA, SAML)?
- Deployment target (self-hosted, cloud platform, edge device)?
- Data retention / privacy requirements (encryption at rest, audit log archival)?

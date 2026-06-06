# Burger Print

A minimal wrapper repository vendoring **[Open WebUI v0.9.6](https://github.com/open-webui/open-webui)** — an open-source AI chat platform with multi-model support, RAG, tools/MCP integration, real-time collaboration, and extensive customization capabilities.

This repo serves as a **base for mockups and customizations** — the full Open WebUI feature set (FastAPI backend ~180K LOC, SvelteKit frontend ~126K LOC) is available under `src/open-webui/` (~310K LOC total).

## Quick Start

### BurgerMockup MCP Server
Start the MCP server to enable design→mockup generation tools (CV composition, SSIM gate):
```bash
cd burgermockup-mcp-server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m server.main
```
Server binds to `http://127.0.0.1:8101/mcp`. OpenWebUI connects natively via `http://host.docker.internal:8101/mcp` from Docker containers. Port 8101 avoids colliding with the hack-burger dev copy on 8100 (set in `.env`).

### Docker Compose (Recommended)
```bash
cd src/open-webui
docker compose up -d
```
Open http://localhost:8080 in your browser.

### Development Mode
```bash
cd src/open-webui
npm install
npm run dev &         # Frontend on http://localhost:5173
cd backend && ./dev.sh  # Backend on http://localhost:8000
```

### With Ollama (Local LLMs)
```bash
docker compose -f docker-compose-launcher.sh up -d
# Auto-detects GPU (NVIDIA/AMD/CPU)
```

## Repository Structure

```
BurgerMockup/
├── burgermockup-mcp-server/ # FastMCP server with 5 MCP tools for design→mockup CV pipeline
│   ├── server/              # Python 3.12 MCP tools + SSIM gate + composition
│   ├── requirements.txt      # fastmcp==3.4.1, mcp==1.27.2 (pinned)
│   ├── .env.example         # Env template (no auth required)
│   └── README.md            # MCP server documentation
├── src/open-webui/          # Vendored Open WebUI v0.9.6 (~310K LOC)
│   ├── backend/             # FastAPI server + SQLAlchemy + Alembic
│   ├── src/                 # SvelteKit frontend (Svelte 5, TypeScript)
│   ├── Dockerfile           # Multi-stage: Node 22 → Python 3.11-slim
│   ├── docker-compose*.yml  # Variants: base, gpu, api, data, otel
│   ├── package.json         # Frontend deps + scripts
│   └── pyproject.toml       # Backend deps (FastAPI, SQLAlchemy, etc.)
├── docs/                    # Documentation (project overview, PDR, architecture)
├── .claude/                 # AI assistant configuration
└── README.md                # This file
```

## Key Capabilities

- **Multi-Model Chat** — OpenAI, Ollama, Mistral, Azure, Bedrock, local + fallback chains
- **RAG (Retrieval-Augmented Generation)** — 9 doc loaders (PDF, web, YouTube, OCR), 15 vector DBs (Pinecone, Qdrant, Chroma, PgVector, Milvus, Weaviate, etc.)
- **Tools & MCP** — Function calling, custom tools, Model Context Protocol integration
- **Real-Time Collaboration** — CRDT-based note editing, live chat streaming via WebSocket
- **Channels & Workspaces** — Organize chats, share models, manage knowledge bases
- **Extensibility** — Pluggable authentication (OAuth/OIDC), custom pipeline middleware, skill automation

## Deployment

| Method | Command | Best For |
|--------|---------|----------|
| **Docker Compose** | `docker compose up` | Local dev, testing |
| **Docker with Ollama** | `docker-compose-launcher.sh` | Local LLMs, GPU auto-detect |
| **Multi-container** | `docker-compose.yml` (db, redis, api, ui) | Production staging |
| **Development** | `npm run dev` + `./dev.sh` | Active development |

**Key env vars:**
- `OLLAMA_BASE_URL` — Ollama endpoint (default: http://localhost:11434)
- `WEBUI_SECRET_KEY` — Session encryption (auto-generated if absent)
- `CORS_ALLOW_ORIGIN` — Allowed origins (dev: `*`, prod: restrict)
- `VECTOR_DB` — Vector store backend (default: chroma; also: pgvector, qdrant, pinecone, etc.)

Port: **8080** (Docker) or **5173** (dev frontend) + **8000** (dev backend).

## Documentation

- **[Project Overview & PDR](./docs/project-overview-pdr.md)** — Project goals, architecture assumptions, feature inventory
- **[Codebase Summary](./docs/codebase-summary.md)** — Directory map, LOC stats, router/component catalog
- **[Code Standards](./docs/code-standards.md)** — Backend/frontend conventions, linting, file organization
- **[System Architecture](./docs/system-architecture.md)** — Data flow, middleware stack, RAG pipeline, deployment topology
- **[Deployment Guide](./docs/deployment-guide.md)** — Docker args, compose variants, startup scripts, config reference
- **[Project Roadmap](./docs/development-roadmap.md)** — Phases, milestones, customization roadmap

## Development

**Linting & Formatting:**
```bash
npm run format          # Prettier (frontend)
npm run format:backend  # Ruff (Python)
npm run lint            # ESLint + Pylint + type check
```

**Testing:**
```bash
npm run test:frontend   # Vitest
# Backend: pytest (no tests in base, but framework ready)
```

**Healthcheck:**
```bash
curl http://localhost:8080/health
```

## License

This wrapper repo includes vendored Open WebUI v0.9.6 (see `src/open-webui/LICENSE`).

## Support

For Open WebUI docs, issues, and community: https://github.com/open-webui/open-webui

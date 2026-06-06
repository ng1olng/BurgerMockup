# Deployment Guide

## Quick Start

### Docker Compose (Default, Recommended)

```bash
cd src/open-webui
docker compose up -d
```

Open http://localhost:8080 in your browser.

- **Services**: web (FastAPI + SPA), db (PostgreSQL), redis, milvus (vector DB)
- **Data**: Persisted in Docker volumes (compose-owned)
- **Logs**: `docker compose logs -f web`
- **Stop**: `docker compose down`

### Docker Compose with Ollama (Local LLMs)

```bash
./docker-compose-launcher.sh
```

Auto-detects GPU (NVIDIA/AMD) and launches appropriate compose variant:
- **NVIDIA GPU** → `docker-compose-gpu.yml`
- **AMD GPU** → `docker-compose-amdgpu.yml`
- **CPU only** → `docker-compose.yml` with CPU variant

### Standalone Docker Image

```bash
docker build \
  --build-arg USE_CUDA=cu128 \
  --build-arg USE_OLLAMA=true \
  --build-arg USE_EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2" \
  -t open-webui:0.9.6 .
```

Run:
```bash
docker run -d \
  -p 8080:8080 \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -e WEBUI_SECRET_KEY=$(openssl rand -base64 32) \
  -v open-webui-data:/app/backend/data \
  open-webui:0.9.6
```

---

## Build Arguments

| Argument | Values | Default | Purpose |
|----------|--------|---------|---------|
| `USE_CUDA` | `cu117`, `cu121`, `cu128`, `false` | `false` | GPU support (NVIDIA CUDA version) |
| `USE_CUDA_VER` | `cu117`, `cu121`, `cu128` | `cu128` | CUDA version (if `USE_CUDA=true`) |
| `USE_OLLAMA` | `true`, `false` | `false` | Bundle Ollama (local LLM server) |
| `USE_SLIM` | `true`, `false` | `false` | Minimal image (skip pre-download of embedding models) |
| `USE_PERMISSION_HARDENING` | `true`, `false` | `false` | Run as non-root user, restrict permissions |
| `USE_EMBEDDING_MODEL` | HuggingFace model ID | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model for RAG |
| `USE_RERANKING_MODEL` | HuggingFace model ID | `` (disabled) | Reranking model for semantic relevance |
| `USE_AUXILIARY_EMBEDDING_MODEL` | HuggingFace model ID | `TaylorAI/bge-micro-v2` | Secondary embedding model |
| `USE_TIKTOKEN_ENCODING_NAME` | Tiktoken encoding | `cl100k_base` | Token counter encoding |
| `BUILD_HASH` | Git hash / version | `dev-build` | Build identifier |
| `UID` / `GID` | Integer | `0` (root) | Non-root user ID (if hardening enabled) |

### Example Builds

**GPU (NVIDIA CUDA 12.1)**:
```bash
docker build --build-arg USE_CUDA=cu121 -t open-webui:gpu .
```

**With Ollama for local LLMs**:
```bash
docker build --build-arg USE_OLLAMA=true -t open-webui:ollama .
```

**Minimal image (cloud-only models)**:
```bash
docker build --build-arg USE_SLIM=true -t open-webui:slim .
```

**Production (hardened, minimal)**:
```bash
docker build \
  --build-arg USE_SLIM=true \
  --build-arg USE_PERMISSION_HARDENING=true \
  --build-arg BUILD_HASH=v0.9.6-prod \
  -t open-webui:prod .
```

---

## docker-compose Variants

### Base Stack (`docker-compose.yml`)

Services:
- **web** — FastAPI + SPA (port 8080)
- **db** — PostgreSQL 15 (port 5432)
- **redis** — Redis (port 6379)
- **milvus** — Milvus vector DB (port 19530)

Volumes:
- `open-webui-db` — PostgreSQL data
- `open-webui-redis` — Redis persistence
- `open-webui-milvus` — Milvus vector store

Environment Variables (from `.env` or defaults):
- `OLLAMA_BASE_URL` — Ollama endpoint (default: http://localhost:11434)
- `WEBUI_SECRET_KEY` — Session secret (auto-generated if absent)
- `DATABASE_URL` — PostgreSQL connection (default: postgresql://postgres:...)
- `REDIS_URL` — Redis connection (default: redis://redis:6379)
- `VECTOR_DB` — Vector store backend (default: milvus)

### GPU Variant (`docker-compose-gpu.yml`)

Adds GPU device to **web** service:
```yaml
services:
  web:
    runtime: nvidia
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      CUDA_VISIBLE_DEVICES: '0'
```

Use with NVIDIA Docker runtime installed.

### API-Only (`docker-compose-api.yml`)

Services:
- **web** — FastAPI (no SPA; API-only)
- **db**, **redis**, **milvus**

Use when running SPA separately (CDN, separate frontend pod).

### Data Services Only (`docker-compose-data.yml`)

Services:
- **db** — PostgreSQL
- **redis** — Redis
- **milvus** — Milvus
- **opensearch** — Elasticsearch alternative (optional)

Use for microservices deployment (FastAPI in separate pod).

### Observability (`docker-compose-otel.yml`)

Adds Grafana LGTM stack:
- **loki** — Log aggregation (port 3100)
- **grafana** — Dashboards (port 3000)
- **tempo** — Distributed tracing (port 3200)
- **prometheus** — Metrics (port 9090)

FastAPI auto-sends metrics/logs via OTEL.

---

## Startup Scripts

### Production (`start.sh`)

Runs in Docker container; handles:
1. Secret key generation (if `WEBUI_SECRET_KEY` absent)
2. Playwright installation (if `WEB_LOADER_ENGINE=playwright`)
3. Ollama setup (if `USE_OLLAMA_DOCKER=true`)
4. CUDA availability check
5. Uvicorn launch

```bash
# In Dockerfile entrypoint
/app/backend/start.sh
# → Launches: uvicorn open_webui.main:app --host 0.0.0.0 --port 8000
#   (SPA served from /app/dist/)
```

### Development (`dev.sh`)

Relaxed settings for local development:
```bash
cd src/open-webui/backend
./dev.sh
# → Uvicorn with auto-reload, debug=True, CORS=*
```

---

## Environment Variables

### Core Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEBUI_SECRET_KEY` | (auto-generated) | Session encryption key (32+ chars) |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama API endpoint |
| `OPENAI_API_KEY` | (empty) | OpenAI API key (if using GPT models) |
| `DATABASE_URL` | sqlite:///./open-webui.db | SQLAlchemy DB connection |
| `REDIS_URL` | redis://localhost:6379 | Redis connection |
| `VECTOR_DB` | chroma | Vector store backend (chroma, qdrant, pgvector, milvus, etc.) |
| `EMBEDDING_MODEL` | sentence-transformers/all-MiniLM-L6-v2 | Sentence transformer model for RAG |
| `CORS_ALLOW_ORIGIN` | * | CORS allowed origins (comma-separated; restrict in prod) |
| `PORT` | 8000 | Uvicorn port (container: 8080 via nginx) |
| `LOG_LEVEL` | INFO | Python logging level (DEBUG, INFO, WARNING, ERROR) |

### Authentication

| Variable | Purpose |
|----------|---------|
| `ENABLE_OAUTH` | Enable OAuth login (true/false) |
| `OAUTH_PROVIDER` | (google, github, openai, custom) |
| `OAUTH_CLIENT_ID` | OAuth client ID |
| `OAUTH_CLIENT_SECRET` | OAuth client secret |
| `ENABLE_LDAP` | Enable LDAP authentication |
| `LDAP_SERVER_URL` | LDAP server address (e.g., ldap://dc.company.com) |

### RAG & Search

| Variable | Purpose |
|----------|---------|
| `VECTOR_DB_HOST` | Vector DB hostname |
| `VECTOR_DB_PORT` | Vector DB port |
| `VECTOR_DB_API_KEY` | Vector DB API key (if needed) |
| `ENABLE_WEB_SEARCH` | Enable web search (true/false) |
| `TAVILY_API_KEY` | Tavily search API key |
| `MAX_FILE_SIZE` | Max document upload size (bytes; default: 100MB) |

### Deployment

| Variable | Purpose |
|----------|---------|
| `ENV` | Deployment environment (dev, staging, prod) |
| `DEBUG` | Debug mode (true/false; false in prod) |
| `WORKERS` | Uvicorn worker count (default: 4) |
| `WEB_LOADER_ENGINE` | Document loader backend (pdf, playwright, etc.) |
| `USE_OLLAMA_DOCKER` | Bundle Ollama in container (true/false) |
| `USE_CUDA_DOCKER` | Enable GPU support (true/false) |

### Example `.env` File

```bash
# Core
WEBUI_SECRET_KEY=your-super-secret-key-here-min-32-chars
OLLAMA_BASE_URL=http://localhost:11434
DATABASE_URL=postgresql://user:password@postgres:5432/open_webui
REDIS_URL=redis://redis:6379/0
VECTOR_DB=qdrant

# Auth
ENABLE_OAUTH=true
OAUTH_PROVIDER=google
OAUTH_CLIENT_ID=your-google-client-id
OAUTH_CLIENT_SECRET=your-google-client-secret

# RAG
ENABLE_WEB_SEARCH=true
TAVILY_API_KEY=your-tavily-key

# Deployment
ENV=production
DEBUG=false
WORKERS=4
CORS_ALLOW_ORIGIN=https://example.com,https://app.example.com
```

Load via:
```bash
# Docker Compose
echo "WEBUI_SECRET_KEY=$(openssl rand -base64 32)" > .env
docker compose --env-file .env up -d

# Or mount .env into container
docker run --env-file .env open-webui:latest
```

---

## Key Endpoints

### Health & Status

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (200 if OK, 503 if degraded) |
| `/api/health` | GET | Detailed health (dependencies status) |
| `/docs` | GET | Swagger API documentation |
| `/redoc` | GET | ReDoc API documentation |

### Chat API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/chats` | Create new chat | |
| `GET /api/chats` | List user's chats | |
| `GET /api/chats/{id}` | Get chat details | |
| `PUT /api/chats/{id}` | Update chat (title, settings) | |
| `DELETE /api/chats/{id}` | Delete chat | |
| `POST /api/chats/{id}/messages` | Send message (streaming) | |
| `GET /api/chats/{id}/messages` | Get chat messages | |

### Models

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/models` | List available models | |
| `POST /api/models/pull` | Pull model from registry (e.g., Ollama) | |
| `DELETE /api/models/{id}` | Remove model | |

### RAG

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /api/retrieval/search` | Search documents by query | |
| `POST /api/knowledge` | Create knowledge base | |
| `POST /api/files` | Upload document | |
| `GET /api/files/{id}` | Download document | |

### Admin

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/admin/users` | List users (admin only) | |
| `POST /api/admin/models` | Configure model integration | |
| `GET /api/admin/analytics` | Usage analytics | |

---

## Ports & Networking

| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| **8080** | FastAPI | HTTP | Main app (Docker container) |
| **8000** | Uvicorn | HTTP | Dev backend (localhost) |
| **5173** | Vite | HTTP | Dev frontend (localhost) |
| **5432** | PostgreSQL | TCP | Database |
| **6379** | Redis | TCP | Cache & sessions |
| **19530** | Milvus | gRPC | Vector DB |
| **11434** | Ollama | HTTP | Local LLM server |
| **3000** | Grafana | HTTP | Observability dashboards |

### Reverse Proxy Setup (nginx)

```nginx
upstream open_webui {
    server localhost:8080;
}

server {
    listen 443 ssl http2;
    server_name app.example.com;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://open_webui;
        proxy_http_version 1.1;
        
        # WebSocket upgrade
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_read_timeout 3600s;
        proxy_connect_timeout 60s;
    }
}
```

---

## Database Initialization

### PostgreSQL (First Run)

```bash
# Via Docker Compose
docker compose exec db psql -U postgres -c "CREATE DATABASE open_webui;"

# Or manually
psql -h localhost -U postgres -c "CREATE DATABASE open_webui;"
```

### Run Migrations

```bash
cd src/open-webui/backend
alembic upgrade head
```

Alembic tracks schema version; always run on startup.

### Backup & Restore

```bash
# Backup PostgreSQL
docker compose exec db pg_dump -U postgres open_webui > backup.sql

# Restore
docker compose exec -T db psql -U postgres open_webui < backup.sql

# Backup volumes
docker run --rm -v open-webui-db:/data -v $(pwd):/backup \
  alpine tar czf /backup/db-backup.tar.gz -C /data .
```

---

## Scaling & High Availability

### Horizontal Scaling (K8s)

```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: open-webui
spec:
  replicas: 3
  selector:
    matchLabels:
      app: open-webui
  template:
    metadata:
      labels:
        app: open-webui
    spec:
      containers:
      - name: open-webui
        image: open-webui:0.9.6
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          value: postgresql://postgres:pass@postgres-service:5432/open_webui
        - name: REDIS_URL
          value: redis://redis-service:6379
        - name: CORS_ALLOW_ORIGIN
          value: "https://app.example.com"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Load Balancing

- **Frontend** — Static SPA, serve from CDN (CloudFront, Netlify, Cloudflare)
- **Backend** — Round-robin across 3+ replicas (nginx, AWS ALB, K8s Service)
- **Socket.IO** — Redis adapter auto-distributes messages across instances

### Database

- **PostgreSQL** — Use managed service (AWS RDS, Azure Database) or primary-replica setup
- **Redis** — Sentinel or Cluster for HA
- **Vector DB** — Use managed service (Pinecone, Milvus Cloud) or self-hosted with replication

---

## Monitoring & Logging

### Health Checks

```bash
# Basic
curl http://localhost:8080/health

# Detailed
curl http://localhost:8080/api/health
# Returns: { db: "ok", redis: "ok", vector_db: "ok", models: [...] }
```

### Log Aggregation

**Docker Compose**:
```bash
docker compose logs -f web              # FastAPI logs
docker compose logs -f db               # PostgreSQL logs
```

**K8s**:
```bash
kubectl logs deployment/open-webui -f --tail=100
```

**OpenTelemetry** (if observability stack enabled):
```bash
# Grafana dashboards at http://localhost:3000
# Loki logs (search) at http://localhost:3100
# Tempo traces at http://localhost:3200
```

### Metrics

FastAPI auto-exports Prometheus metrics at `/metrics` (if OpenTelemetry enabled).

Key metrics:
- `http_requests_total` — Total API requests
- `http_request_duration_seconds` — Request latency
- `openai_token_usage_total` — Token count by model
- `vector_db_query_duration_seconds` — RAG search latency

---

## Troubleshooting

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| **Port 8080 already in use** | `lsof -i :8080` | `docker compose down` or kill other process |
| **Database connection fails** | Check `DATABASE_URL` in `.env` | Ensure PostgreSQL running, credentials correct |
| **Models won't load** | Check `OLLAMA_BASE_URL` | Verify Ollama running or use cloud API keys |
| **RAG search returns nothing** | Check `VECTOR_DB` type and embedding model | Ensure documents uploaded + indexed |
| **WebSocket timeout** | Reverse proxy timeout too short | Increase proxy timeout to 3600s |
| **Out of memory** | Check container limits | Increase Docker memory limit or reduce model size |
| **Railway: "Railpack could not determine how to build the app" / "Script start.sh not found"** | Build log shows repo root contents (`.claude/`, `docs/`, `src/`) — build context is wrong | Set **Root Directory** = `src/open-webui` in service settings (and Config-as-code path = `src/open-webui/railway.toml`); for CLI use `railway up ./src/open-webui` |

### Debug Mode

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
./dev.sh

# Or in docker-compose.yml
environment:
  LOG_LEVEL: DEBUG
```

---

## Hosting on Railway

Deploy the vendored copy (`src/open-webui/`) to [Railway](https://railway.com) as a single container service. Strategy: Railway builds the Dockerfile directly with `USE_SLIM=true`, SQLite persisted on a Railway volume, LLM served by an external API (no GPU on Railway — bundled Ollama not viable).

### Prerequisites

- Railway account (Hobby plan or above — needs volume support + enough build resources)
- This repo pushed to GitHub (Railway deploys from the GitHub repo)
- Optional: an OpenAI-compatible API key OR an externally reachable Ollama host

### Config-as-Code (`src/open-webui/railway.toml`)

Build/deploy behavior is pinned in `src/open-webui/railway.toml` (builder `DOCKERFILE`, healthcheck `/health` with 600s timeout, `ON_FAILURE` restart). Two settings **cannot** live in the toml and MUST be set in the dashboard:

| Dashboard setting | Value | Why |
|-------------------|-------|-----|
| **Root Directory** (Settings → Source) | `src/open-webui` | Sets the build context — the Dockerfile's `COPY` paths assume it. Without this, Railpack analyzes the repo root and fails with *"could not determine how to build the app"*. |
| **Config-as-code path** (Settings) | `src/open-webui/railway.toml` | Railway does NOT resolve the config file relative to Root Directory — the path is from repo root. |

> ⚠️ Plain `railway up` from the repo root uploads the wrong context and reproduces the Railpack failure. Use GitHub-connected deploys; for CLI experiments run `railway up ./src/open-webui`.

### Step 1 — Create the Service

1. Railway dashboard → **New Project** → **Deploy from GitHub repo** → select this repo
2. Service → **Settings** → **Source**:
   - **Root Directory**: `src/open-webui` (Railway then auto-detects the `Dockerfile` there)
3. Service → **Settings** → set **Config-as-code path** to `src/open-webui/railway.toml`
4. Build args (add under *Variables* — Railway passes service variables to Dockerfile builds automatically where `ARG` is declared):

| Build Arg | Value | Why |
|-----------|-------|-----|
| `USE_SLIM` | `true` | Skips pre-baked embedding/whisper/tiktoken models. Full image is ~5 GB — risks Railway image-size limits and build timeouts. Slim ≈ 1.5–2 GB. RAG embedding model downloads at runtime into the volume instead. |
| `USE_CUDA` | `false` (default) | No GPU on Railway. |
| `USE_OLLAMA` | `false` (default) | Bundled Ollama impractical without GPU + adds GBs. |

Expect **~15–20 min** per build (frontend npm build + pip install). Subsequent builds reuse layer cache when dependencies don't change.

### Step 2 — Attach a Volume

1. Right-click service → **Attach Volume**
2. **Mount path**: `/app/backend/data`

This persists: SQLite DB (`webui.db`), uploaded files, vector DB (Chroma default), and runtime-downloaded embedding models. Without it, **all data is wiped on every redeploy**.

> Railway volumes attach to a single replica — keep **replicas = 1** (also required by SQLite + the default in-memory socket manager).

### Step 3 — Set Environment Variables

Service → **Variables**:

| Variable | Value | Required | Notes |
|----------|-------|----------|-------|
| `WEBUI_SECRET_KEY` | long random string (`openssl rand -hex 32`) | **Yes** | ⚠️ If unset, `start.sh` generates a key into the container filesystem (NOT the volume) — every redeploy invalidates all sessions/JWTs. |
| `ENV` | `prod` | Yes | Production mode. |
| `FORWARDED_ALLOW_IPS` | `*` | Yes | Railway terminates TLS at its proxy; uvicorn must trust forwarded headers. |
| `WEBUI_URL` | `https://<your-domain>.up.railway.app` | Recommended | Correct links in emails/shares. |
| `ENABLE_PERSISTENT_CONFIG` | `true` (default) | — | Config stored in DB on the volume. |

`PORT` is injected by Railway automatically — `backend/start.sh:33` (`PORT="${PORT:-8080}"`) honors it. No override needed.

#### LLM Backend (pick one when ready)

| Option | Variables |
|--------|-----------|
| OpenAI-compatible API (OpenAI, OpenRouter, etc.) | `OPENAI_API_BASE_URL=https://api.openai.com/v1`, `OPENAI_API_KEY=sk-...` |
| External Ollama (home server / GPU VPS, must be reachable over HTTPS) | `OLLAMA_BASE_URL=https://ollama.example.com` |

Both can also be configured later in **Admin Panel → Settings → Connections** (persisted to the volume-backed DB).

### Step 4 — Networking & Health Check

1. Service → **Settings** → **Networking** → **Generate Domain** (public HTTPS URL)
2. Service → **Settings** → **Deploy**:
   - **Healthcheck Path**: `/health`
   - **Healthcheck Timeout**: ≥ 300s (first boot runs Alembic migrations + may download the embedding model)

### Step 5 — First Boot

1. Open the generated domain → **Sign up** — the **first account becomes admin**
2. Verify version in **Admin Panel → Settings → About** (expect v0.9.6)
3. Wire up the LLM connection (Step 3 table) and send a test chat

### Railway Caveats

| Caveat | Detail |
|--------|--------|
| **Single replica only** | SQLite + volume + in-memory socket manager all break with >1 replica. Scaling out requires `DATABASE_URL` (Postgres), `REDIS_URL` + websocket manager, and external vector DB — see scale-up path. |
| **Build time** | ~15–20 min per push. Acceptable for a mockup; for faster iteration move builds to GitHub Actions → GHCR and have Railway deploy the image instead. |
| **Volume backups** | Railway volume snapshots are manual — back up `webui.db` periodically (Railway CLI `railway ssh` + `sqlite3 .backup`, or download via admin DB export). |
| **Cold RAG start** | Slim image downloads the embedding model (~80 MB, `all-MiniLM-L6-v2`) on first RAG use — one-time delay, cached on the volume. |
| **Egress costs** | LLM API traffic + model downloads count toward Railway egress. |

### Scale-Up Path (when mockup outgrows this)

1. **Railway Postgres** service → set `DATABASE_URL` (migrates off SQLite)
2. **Railway Redis** service → set `REDIS_URL` + `WEBSOCKET_MANAGER=redis` (enables multi-replica websockets)
3. External vector DB (e.g. pgvector on the same Postgres: `VECTOR_DB=pgvector`)
4. CI-built images: GitHub Actions → GHCR → Railway image deploys (cuts deploy time to ~1 min)

---

## Hosting the MCP server on Railway

Deploy `src/burgermockup-mcp-server` as a **second service in the same Railway project** as
Open WebUI. The server has no built-in auth, so the public deployment is protected by a shared
Bearer token (`MCP_AUTH_TOKEN`); Open WebUI sends it natively as the MCP connection's API key.

Config-as-code: `src/burgermockup-mcp-server/railway.toml` (builder `DOCKERFILE`, healthcheck
`/health`, `ON_FAILURE` restart). Dashboard prerequisite: **Root Directory** =
`src/burgermockup-mcp-server` (or deploy via `railway up ./src/burgermockup-mcp-server`, which
uploads that dir as the build context directly).

### Security model

- The Bearer gate (`server/auth_middleware.py`) enforces `Authorization: Bearer $MCP_AUTH_TOKEN`
  on `/mcp` + the mutation routes (`/designs`, `/jobs/...`).
- **Exempt by design:** `/health` (Railway probe sends no header) and `/files/{id}` (rendered in
  the user's browser via `<img>`, which can't carry an auth header — file ids are UUID-keyed, so
  unguessable but **not** authenticated; acceptable for a controlled demo, not for sensitive media).
- The gate **self-disables** when `MCP_AUTH_TOKEN` is unset/blank — local loopback and
  `docker-compose.mcp.yaml` (which pass no token) keep working unchanged.
- Token compare is constant-time (`hmac.compare_digest` on raw bytes).

### Step 1 — Create the service

```bash
railway up ./src/burgermockup-mcp-server      # in the linked project; deploys to the linked service
```
First boot may fail its healthcheck until env (Step 2) is set — that's expected; redeploy fixes it.

### Step 2 — Volume, domain, env

1. **Attach Volume** → mount path `/data` (covers `/data/files` + `/data/metrics`). **Single replica** (local file store).
2. **Settings → Networking → Generate Domain** → note `https://<mcp>.up.railway.app`.
3. **Variables:**

   | Variable | Value | Notes |
   |----------|-------|-------|
   | `MCP_AUTH_TOKEN` | `openssl rand -hex 32` | **Save it** — Open WebUI needs the same value. |
   | `PUBLIC_FILES_BASE` | `https://<mcp>.up.railway.app` | Base for returned file links. **Chicken-and-egg:** domain unknown until the service exists → set after Step 2.2, then **redeploy**. |
   | `GEMINI_API_KEY` | paid key | Optional — mockup generation is inert until set. |

   `PORT` is injected by Railway; `run()` binds it (`PORT` → `MCP_PORT` → `8100`). `FILES_DIR=/data/files`
   and `MCP_BIND_HOST=0.0.0.0` are already set as Dockerfile ENV.
4. **Redeploy** so `PUBLIC_FILES_BASE` + token take effect.

### Step 3 — Wire Open WebUI → MCP

In Open WebUI: **Admin → Settings → External Tools → add MCP (Streamable HTTP)**:
- **URL:** `https://<mcp>.up.railway.app/mcp`
- **Auth:** Bearer / API Key = the `MCP_AUTH_TOKEN` value.

Save → the 5 tools (register_design, match_product, generate_mockups, refine_mockups,
export_listing) appear.

### Verify

```bash
curl -s https://<mcp>.up.railway.app/health                                   # {"ok": true}
curl -s -o /dev/null -w "%{http_code}\n" https://<mcp>.up.railway.app/mcp     # 401 (no token)
```
Then confirm a returned `/files/{id}` link renders in the browser, and a tool call from Open
WebUI succeeds (token accepted, streaming passes through the gate).

---

## Unresolved Questions

- Recommended vector DB for production (self-hosted vs managed)?
- Database replication strategy for multi-region?
- Cost optimization (how many replicas, data transfer, storage)?
- Disaster recovery RTO/RPO targets?

# Code Standards & Conventions

## Overview

This document codifies conventions observed in the vendored Open WebUI codebase and standards required for custom code in future phases.

**Applies to**: Custom code added outside `src/open-webui/` (or explicitly customized modules within). Open WebUI's own code is immutable.

---

## Backend (FastAPI / Python)

### Async-First Design

- All handlers **must be `async def`**; use `async` context managers and await
- Use `anyio.to_thread.run_sync()` for blocking I/O (file reads, CPU-heavy ops)
- Do not block the event loop; test with `asyncio-timeout`

**Example:**
```python
@router.get("/items/{item_id}")
async def get_item(item_id: str):
    # Async I/O
    data = await db.fetch(f"SELECT * FROM items WHERE id = {item_id}")
    return JSONResponse(data)
```

### SQLAlchemy ORM (2.0 async)

- Use `async_sessionmaker` + `AsyncSession` for DB access
- Define models as `sqlalchemy.orm.declarative_base()` classes
- Use relationships with lazy loading (`selectinload`, `joinedload` for eager fetch)
- Migrations via Alembic; test schema changes before merging

**Example:**
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select

async def get_user(session: AsyncSession, user_id: int):
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

### Router Pattern

- One file per router/domain (`routers/users.py`, `routers/chats.py`)
- Prefix routes: `@router.get("/users/{id}")`
- Mount routers in `main.py`: `app.include_router(users.router, prefix="/api/users")`
- Use Pydantic models for request/response schemas

**Example:**
```python
# routers/items.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["items"])

@router.get("/{id}")
async def get_item(id: int, session: AsyncSession = Depends(get_db)):
    return await db_get_item(session, id)
```

### Error Handling & Validation

- Use Pydantic for request validation (auto 422 Unprocessable Entity on schema failure)
- Raise `HTTPException(status_code=..., detail=...)` for API errors
- Catch `SQLAlchemy.exc.*` and log with context; return generic 500 to client (no schema leaks)
- Use try/except for external service calls (OpenAI, search APIs); fallback gracefully

**Example:**
```python
from fastapi import HTTPException

try:
    result = await openai_client.chat.completions.create(...)
except openai.RateLimitError:
    raise HTTPException(status_code=429, detail="Rate limited")
except openai.APIError as e:
    logger.error(f"OpenAI error: {e}")
    raise HTTPException(status_code=502, detail="Service unavailable")
```

### Dependency Injection (FastAPI Depends)

- Use `Depends()` for auth, DB sessions, config, logging
- Define reusable dependency functions at module top

**Example:**
```python
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    # Verify JWT, return user or raise HTTPException
    pass

@router.get("/me")
async def get_my_profile(user: User = Depends(get_current_user)):
    return user
```

### Middleware & Interceptors

- Middleware in `utils/middleware.py`; mount in `main.py` with `app.add_middleware()`
- Use request state for thread-safe context (user, request ID, timing)

**Example:**
```python
from starlette.middleware.base import BaseHTTPMiddleware

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user_id = extract_user(request)
        response = await call_next(request)
        return response

app.add_middleware(AuditMiddleware)
```

### Alembic Migrations

- One change per migration file (naming: `alembic/versions/001_init.py`)
- Test migrations locally (up + down)
- Never modify an existing migration; create a new one
- Use `alembic upgrade head` before deployment

**Example:**
```bash
alembic revision --autogenerate -m "add_user_email_column"
alembic upgrade head
```

### Imports & Organization

- Standard library imports, then third-party, then local
- One import per line for clarity (OK to group from same module)
- Avoid circular imports; use TYPE_CHECKING for type hints

```python
from typing import TYPE_CHECKING
import asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from models import User
```

---

## Frontend (SvelteKit / Svelte 5 / TypeScript)

### Component Structure

- One component per file (PascalCase: `ChatInput.svelte`, `MessageList.svelte`)
- Keep components under 150–200 lines; extract logic to stores or functions
- Use `<script>` with `let`, reactive variables, functions
- Use `<svelte:options immutable />` for performance if applicable

**Example:**
```svelte
<!-- ChatInput.svelte -->
<script>
	import { chats } from '$lib/stores';
	
	let message = '';
	
	async function sendMessage() {
		if (!message.trim()) return;
		await chats.addMessage(message);
		message = '';
	}
</script>

<div class="input-container">
	<input
		bind:value={message}
		on:keydown={(e) => e.key === 'Enter' && sendMessage()}
		placeholder="Type a message..."
	/>
	<button on:click={sendMessage}>Send</button>
</div>

<style>
	.input-container {
		display: flex;
		gap: 0.5rem;
	}
</style>
```

### Stores (Svelte Writable)

- Centralized in `lib/stores/index.ts`
- Use `writable()` for mutable state, `derived()` for computed
- Export store subscriptions as typed getters/setters if complex

**Example:**
```typescript
// lib/stores/index.ts
import { writable, derived } from 'svelte/store';

export const user = writable<User | null>(null);
export const chats = writable<Chat[]>([]);

export const activeChat = derived(
	chats,
	($chats) => $chats.find(c => c.active) || null
);
```

### API Modules (fetch + Bearer auth)

- One module per domain: `lib/apis/chats.ts`, `lib/apis/models.ts`
- Fetch with Bearer token from store/config
- Use EventSource for streaming responses

**Example:**
```typescript
// lib/apis/chats.ts
import { config } from '$lib/stores';

export async function sendMessage(chatId: string, message: string) {
	const token = get(config).token;
	const res = await fetch(`/api/chats/${chatId}/messages`, {
		method: 'POST',
		headers: { 'Authorization': `Bearer ${token}` },
		body: JSON.stringify({ content: message })
	});
	return res.json();
}

export function streamChatResponse(chatId: string, onChunk: (chunk: string) => void) {
	const token = get(config).token;
	const source = new EventSource(`/api/chats/${chatId}/stream?token=${token}`);
	source.onmessage = (e) => onChunk(e.data);
	return source;
}
```

### Route Organization

- `src/routes/(app)/` — Auth-gated pages
- `src/routes/auth/` — Public auth pages
- `src/routes/+layout.svelte` — Root layout (socket init, store bootstrap)
- Use `+page.svelte` for page content, `+layout.svelte` for wrapper

**Example:**
```
src/routes/
├── +layout.svelte       # Root: socket, stores
├── +page.svelte         # Home (public)
├── (app)/
│   ├── +layout.svelte   # Auth gate
│   ├── +page.svelte     # Dashboard
│   ├── c/[id]/
│   │   └── +page.svelte # Chat page
├── auth/
│   └── login/
│       └── +page.svelte # Login form
```

### TypeScript Best Practices

- Always define interfaces for data models
- Use strict mode: `"strict": true` in tsconfig.json
- Prefer `type` for objects, `interface` for extensible APIs
- Avoid `any`; use `unknown` with type guards

**Example:**
```typescript
interface User {
	id: string;
	name: string;
	email: string;
}

interface ChatMessage {
	id: string;
	chatId: string;
	content: string;
	sender: User;
	timestamp: Date;
}

export async function getMessages(chatId: string): Promise<ChatMessage[]> {
	const res = await fetch(`/api/chats/${chatId}/messages`);
	return res.json() as Promise<ChatMessage[]>;
}
```

### Styling (Tailwind CSS + Svelte)

- Use Tailwind utility classes; minimize custom CSS
- Component-scoped styles OK, but prefer utility-first
- Dark mode: use `dark:` prefix for dark mode variants
- Responsive: use `sm:`, `md:`, `lg:` breakpoints

```svelte
<div class="flex gap-4 md:gap-8 dark:bg-slate-800">
	<button class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
		Click me
	</button>
</div>
```

### Internationalization (i18next)

- Store translations in `src/lib/i18n/{locale}.json`
- Load lazily per locale
- Use `$t('key')` in components after init

**Example:**
```typescript
// lib/i18n.ts
import i18next from 'i18next';

await i18next.init({
	fallbackLng: 'en',
	ns: ['common'],
	defaultNS: 'common',
	backend: { loadPath: '/locales/{{lng}}/{{ns}}.json' }
});
```

---

## This Repository (Custom Code Only)

### File Naming

- **Kebab-case** for all filenames: `user-auth.ts`, `chat-input.svelte`, `message-handler.py`
- **Long, descriptive names** are encouraged (clarity over brevity for LLM tooling)
- Example: `rag-document-loader.py` (not `loader.py`)

### File Size Limits

- **Python/TypeScript files**: < 200 lines for new code
- **Svelte components**: < 150 lines (script + template)
- **SQL/config files**: No limit, but keep logical sections < 100 lines each
- Modularize early; extract functions/classes before hitting limit

### Code Comments

- Comment the **why**, not the what (code is self-documenting)
- Avoid plan/phase references (e.g., "per phase 3 RAG work") — not stable
- Link to related code or external docs where helpful

**Good:**
```python
# Org-scoped advisory lock serializes concurrent chat reassigns
# without requiring distributed locks (schema: users.chat_lock_id)
async def acquire_chat_lock(user_id: str):
    ...
```

**Avoid:**
```python
# per F13 advisory-lock fix
# Per phase-03 RAG work
async def acquire_chat_lock(user_id: str):
    ...
```

### YAGNI / KISS / DRY

- **YAGNI**: Don't add features you might need later (e.g., multi-tenancy until required)
- **KISS**: Prefer simple solutions; avoid over-engineering
- **DRY**: Extract repeated patterns; don't copy-paste logic across files

### Git Commits

- Use **conventional commits**: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- One logical change per commit
- No AI references (e.g., no "Generated by Claude" in commit message)
- Example: `feat: add user email validation to auth router`

### Linting & Formatting

#### Frontend
```bash
npm run lint            # ESLint (auto-fix)
npm run format          # Prettier
npm run check           # Svelte type checking
npm run test:frontend   # Vitest
```

**Config**:
- `.eslintrc.json` — ESLint rules
- `.prettierrc` — Prettier formatting
- `tsconfig.json` — TypeScript strict mode

#### Backend
```bash
ruff check backend/
ruff format backend/
pylint backend/
pytest backend/tests/
```

**Config**:
- `pyproject.toml` — Ruff + Pylint rules

### Documentation in Code

- **Docstrings (Python)**: Google-style for functions/classes
- **JSDoc (TypeScript)**: For exported functions, interfaces
- **README per module**: Large subsystems (RAG, auth) deserve a `README.md`

**Python docstring:**
```python
async def embed_documents(documents: list[str], model: str = "all-MiniLM-L6-v2") -> list[list[float]]:
    """Embed documents using a sentence transformer.
    
    Args:
        documents: List of text documents to embed.
        model: HuggingFace sentence transformer model ID.
    
    Returns:
        List of embedding vectors (one per document).
    
    Raises:
        ValueError: If documents list is empty.
    """
    ...
```

**TypeScript JSDoc:**
```typescript
/**
 * Send a message to a chat.
 * @param chatId - The chat ID.
 * @param content - Message content.
 * @returns The created message object.
 */
export async function sendMessage(chatId: string, content: string): Promise<ChatMessage> {
    ...
}
```

### Testing Strategy

- **Unit tests**: Module-level logic (formatters, validators, utils)
- **Integration tests**: Router + DB roundtrips, API endpoints
- **E2E tests**: Critical user journeys (login, send message, RAG query)
- **Mocking**: Mock external services (OpenAI, search APIs); use real DB in tests (SQLite in-memory)

**Example (Python pytest):**
```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with AsyncSession(engine) as session:
        yield session

@pytest.mark.asyncio
async def test_create_user(db):
    user = await create_user(db, "alice@example.com")
    assert user.email == "alice@example.com"
```

### Security Checklist

- No secrets in code (use env vars + `.env.local` gitignored)
- Validate all user input (Pydantic for FastAPI, form validation in Svelte)
- Use HTTPS in production (CORS, CSP headers)
- Sanitize HTML output (DOMPurify in frontend, Bleach in Python if needed)
- Rate-limit public endpoints
- Log security events (failed auth, permission denied)

---

## Conventions Inherited from Open WebUI

### Backend Patterns
- Config management via `config.py` (env-backed, hot-reloadable)
- Access control via `utils/access_control.py` (RBAC + attribute-based)
- RAG pipeline: loaders → embeddings → vector DB (pluggable backends)
- Socket.IO for real-time (Redis-distributed)
- Alembic for safe schema evolution

### Frontend Patterns
- Centralized stores for app state (Svelte writable stores)
- API modules with consistent fetch + Bearer auth pattern
- Domain-based component organization (chat, admin, workspace, etc.)
- i18next for translations
- Tailwind CSS first; minimize component-scoped styles
- TypeScript for type safety

### Deployment
- Multi-stage Docker (Node 22 → Python 3.11-slim)
- Environment-driven config (no recompile for different deployments)
- docker-compose variants (base, GPU, API-only, data-only, observability)
- Health check endpoint (`/health`)
- Graceful shutdown (clean up connections, finish in-flight requests)

---

## Unresolved Questions

- Custom authentication flow (does Burger need proprietary auth, or use Open WebUI's oauth2_scheme)?
- Rate limiting strategy (per-user, per-IP, or model-aware)?
- Test coverage target (80%, 90%)?
- Custom styling guide (Burger brand colors, typography)?

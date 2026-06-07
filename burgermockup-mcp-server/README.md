# BurgerMockup MCP Server

FastMCP server that turns a seller's design image + a BurgerPrints catalog
product into print-on-demand mockups, conversationally. The seller never picks
from a dropdown — the calling LLM resolves product mentions, registers the
design, and generates/refines mockups through the tools below.

## `server/tools/` — Tool Layer

The MCP-exposed tools and the OpenAI-compatible image endpoint. This layer owns
**input validation, server-side invariants, and error shaping** — none of it is
trusted to the LLM. Tools are registered in [`server/main.py`](server/main.py)
via `mcp.tool(...)`; shapes (`SceneSpec`, `VariantResult`, `tool_error`,
`MAX_VARIANTS`) live in [`server/contracts.py`](server/contracts.py).

| File | Symbol(s) | Exposed as | Status |
|------|-----------|-----------|--------|
| [`catalog_tools.py`](server/tools/catalog_tools.py) | `match_product` | MCP tool | ✅ |
| [`design_tools.py`](server/tools/design_tools.py) | `register_design` | MCP tool | ✅ |
| [`mockup_tools.py`](server/tools/mockup_tools.py) | `generate_mockups`, `refine_mockups` | MCP tools | ✅ |
| [`export_tools.py`](server/tools/export_tools.py) | `export_listing` | MCP tool | 🚧 stub |
| [`image_gen_compat.py`](server/tools/image_gen_compat.py) | `handle_image_generations` | `POST /v1/images/generations` | ✅ |

### Typical agent flow

```
match_product("áo thun trắng")   → product_id
register_design(image_base64, …)  → design_id      (or POST /designs multipart)
generate_mockups(job_id, design_id, product_id, scene_specs, n)
refine_mockups(...)               → adjust scale / regenerate scene / swap product
```

---

### `match_product(query: str) -> dict`

Fuzzy VN/EN match of a natural-language product mention against the cached
catalog. The agent calls this instead of asking the user to choose from a list.

- **Returns:** `{"candidates": [{product_id, name, type, colors[], score, composable}]}`. Empty list = no match.
- **Errors:** `empty_query`.
- `composable` flags whether the product has an annotated print area (a quad), i.e. whether `generate_mockups` will work on it.

### `register_design(image_base64: str, filename: str) -> dict`

Registers a design image (PNG/JPG/WebP, ≤25 MB). **base64 only** — URL fetching
was removed deliberately (an LLM-constructed URL is an SSRF primitive); the
browser path uploads multipart via `POST /designs` instead.

- **Returns:** `{design_id, width, height, has_alpha, text_heavy}`.
- **Errors:** `invalid_encoding`, plus `file_store.IngestError` codes (size/format).
- Design pixels are kept **100% intact** — never sent through an image-generation model.

### `generate_mockups(job_id, design_id, product_id, scene_specs, n, ctx) -> dict`

Generates `n` mockup variants. Streams per-variant progress via MCP progress
notifications; ready variants also carry their image `url` in the result
(host clients like Open WebUI drop progress notifications, so the result is the
only channel that reliably reaches the model).

- **Returns:** `{"variants": [VariantResult]}` where each is `{variant_id, scene_id, status: ready|failed, ssim?, url?, degraded}`.
- **Errors:** `design_not_found`, `product_not_found`, `no_print_area`, `invalid_n`.
- **Invariants (server-enforced):** `n` clamped to `MAX_VARIANTS` (8); negative constraints injected server-side; abort checked between variants; one variant's failure never kills the batch.
- `scene_specs` map to `SceneSpec` fields (`niche`, `setting`, `lighting`, `mood`, `camera`, `composition`, `style`, …). Empty spec → flat mockup on the catalog base; a scene spec → lifestyle render (when a scene model is configured).
- `degraded: true` = a scene was requested but the variant fell back to flat (scene model failing); consumers must disclose this.

### `refine_mockups(job_id, design_id, product_id, variants, delta, ctx) -> dict`

Follow-up adjustment of existing variants. Same result/progress shape as
`generate_mockups`.

- **`delta.type`:** `design` (reuse scenes, no image-model call) · `scene` (regenerate scenes) · `product` (new garment).
- **`delta.scale`** (0.3–1.6): resizes the printed design (1.0 = unchanged).
- **`delta.target_ordinal`** (1-based): limits the refine to one variant; omit for all.
- **Errors:** `invalid_delta`, `no_variants`, `invalid_scale`, `invalid_ordinal`, `ordinal_out_of_range`.
- A `design` delta keeps the spec empty so a cache miss recomposites on the flat base rather than calling the model; a cached-scene refine never silently changes the scene.

### `export_listing(variant_ids: list[str]) -> dict` — 🚧 stub

Roadmap feature (zip + `listing.json`). Currently returns
`{status: "not_implemented", ...}`. When built it must validate every
`variant_id` against the caller-supplied set and name zip members from
server-side constants (`mockup_01.png`), never from caller strings.

### `handle_image_generations(body: dict) -> (dict, int)` — OpenAI-compatible

Drop-in OpenAI image backend (Path A — pure Gemini pass-through, no compositor
or SSIM gate). Wired to `POST /v1/images/generations` in `main.py`. The prompt
is passed verbatim to Gemini against a blank white 512×512 base.

- **Returns:** `({created, data: [{url}|{b64_json}]}, 200)` or `({error: {code, message}}, status)`.
- **Errors:** `invalid_prompt` (400), `not_configured` (503, no `GEMINI_API_KEY`), `invalid_n` (400), `generation_failed` (502), `internal_error` (500). `n` capped at 4.
- OWUI config: `IMAGE_GENERATION_ENGINE=openai`, `IMAGES_OPENAI_API_BASE_URL=http://127.0.0.1:8100/v1`.

---

## Error & message discipline

- All tool errors go through `tool_error(code, message)` → `{"error": {"code", "message"}}`.
- `message` is **always a fixed string** — provider/OS error bodies are never echoed (they reach the LLM and the browser). Full tracebacks are logged server-side only.

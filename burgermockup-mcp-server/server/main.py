"""burgermockup-mcp-server — assembly.

5 MCP tools over streamable HTTP (bind 127.0.0.1: the server has no auth, so
it is never exposed beyond the local machine / compose network) plus three
HTTP side-channels:
  POST /designs            multipart upload (browser path; avoids base64 inflation)
  GET  /files/{file_id}    UUID-validated file serving (never path-joined)
  POST /jobs/{job_id}/abort  host-controlled abort for in-flight generation
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

# Bare-metal dev runs get env from .env; without this GEMINI_API_KEY/BP_API_KEY
# are invisible and every lifestyle variant silently degrades to flat.
# override=True: the service's own .env must beat ambient shell exports — a
# stale global GEMINI_API_KEY in ~/.zshrc shadowed the paid key here and every
# scene call 429'd while direct probes with the .env key succeeded. Docker is
# unaffected: images exclude .env (.dockerignore), so injected env still rules.
load_dotenv(override=True)

# Root handler for all server.* loggers (fastmcp's rich handler is attached to
# its own logger and does not cover ours). Console-only by design: Docker and
# the dev terminal both capture stderr.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
)

from server import jobs  # noqa: E402
from server.storage import file_store
from server.tools.catalog_tools import match_product
from server.tools.design_tools import register_design
from server.tools.export_tools import export_listing
from server.tools.image_gen_compat import handle_image_generations
from server.tools.mockup_tools import generate_mockups, refine_mockups

mcp = FastMCP(
    "burgermockup",
    instructions=(
        "BurgerMockup — AI mockup generator for print-on-demand products.\n\n"
        "## Required call order\n\n"
        "1. **match_product(query)** — resolve a natural-language product name (VN or EN) to a "
        "`product_id`. Always run this first; never guess a product_id.\n\n"
        "2. **register_design(image_base64, filename)** — upload the seller's design image and "
        "receive a `design_id`. Skip this step only if the message already contains a "
        "`design registered: design_id=...` annotation (injected automatically by the "
        "BurgerMockup design-bridge filter when the user attaches an image).\n\n"
        "3. **generate_mockups(job_id, design_id, product_id, scene_specs, n)** — generate up "
        "to 8 variants. Requires both `design_id` (step 2) and `product_id` (step 1). "
        "Use a fresh UUID for `job_id`. Each ready variant in the result contains a `url` — "
        "render it inline: ![variant](url).\n\n"
        "4. **refine_mockups(...)** — optional follow-up to adjust design scale, regenerate "
        "scenes, or swap the product. Pass the `variants` list returned by step 3.\n\n"
        "5. **export_listing(variant_ids)** — not yet available; returns not_implemented.\n\n"
        "## Example — 'Tạo tshirt với design này, áo màu trắng'\n\n"
        "User attaches an image and asks to create a white t-shirt mockup.\n\n"
        "```\n"
        "# Step 1 — design_id already injected by the filter (image was attached):\n"
        "# [design registered: design_id=abc123 ...] ← read from message, skip register_design\n\n"
        "# Step 2 — resolve product\n"
        "match_product(query='tshirt trắng')\n"
        "# → product_id='unisex-tshirt-01'\n\n"
        "# Step 3 — generate mockup with white color hint in scene_specs\n"
        "generate_mockups(\n"
        "    job_id='<uuid>',\n"
        "    design_id='abc123',\n"
        "    product_id='unisex-tshirt-01',\n"
        "    scene_specs=[{'setting': 'studio white background', 'lighting': 'soft'}],\n"
        "    n=2\n"
        ")\n"
        "# → display each variant url as ![variant](url)\n"
        "```\n\n"
        "## scene_specs — generating diverse variants\n\n"
        "Each element in `scene_specs` is a `SceneSpec` object with these optional fields:\n"
        "`niche`, `setting`, `model_persona`, `lighting`, `mood`, `market`,\n"
        "`camera`, `composition`, `style`, `film_look`.\n\n"
        "Built-in niches (use as `niche` value): cafe, streetwear, yoga, cozy, picnic, "
        "flat-lay, christmas, christmas-outdoor, christmas-gifting.\n\n"
        "**For a 3-scene Christmas batch** (e.g. user says '3 scene mùa lễ'), pass three "
        "distinct specs — one per sub-variant — to get meaningfully different backgrounds:\n\n"
        "```\n"
        "scene_specs=[\n"
        "  {'niche': 'christmas'},\n"
        "  {'niche': 'christmas-outdoor'},\n"
        "  {'niche': 'christmas-gifting'},\n"
        "]\n"
        "```\n\n"
        "You may also add `camera`, `composition`, `style`, or `film_look` to any spec "
        "for cinematic quality when the user asks for editorial/premium output:\n\n"
        "```\n"
        "{'niche': 'christmas', 'style': 'editorial lifestyle',\n"
        " 'camera': 'Canon EOS R5, 85mm, f/1.8', 'film_look': 'warm film grain'}\n"
        "```\n\n"
        "## Rules\n"
        "- Never call generate_mockups without a registered design_id.\n"
        "- Never fabricate product_id; always call match_product first.\n"
        "- When user mentions a color (trắng/đen/xanh/...), pass it as `setting` or `mood` in "
        "scene_specs — do NOT pass it as a separate tool argument.\n"
        "- Never pass caller-supplied strings as negative_constraints; these are injected "
        "server-side automatically.\n"
        "- Display every variant url as a markdown image immediately after generation."
    ),
)
# Logs every MCP request/tool call with args. Payloads here are IDs and scene
# specs only — never secrets or image bytes — so they are safe on the console.
mcp.add_middleware(LoggingMiddleware(include_payloads=True))

mcp.tool(register_design)
mcp.tool(match_product)
mcp.tool(generate_mockups)
mcp.tool(refine_mockups)
mcp.tool(export_listing)


@mcp.custom_route("/v1/images/generations", methods=["POST"])
async def openai_image_generations(request: Request) -> JSONResponse:
    """OpenAI-compatible image generation endpoint for OWUI / any OpenAI client.

    Configure OWUI: IMAGE_GENERATION_ENGINE=openai,
    IMAGES_OPENAI_API_BASE_URL=http://127.0.0.1:8100/v1
    """
    body = await request.json()
    result, status_code = await handle_image_generations(body)
    return JSONResponse(result, status_code=status_code)


@mcp.custom_route("/designs", methods=["POST"])
async def upload_design(request: Request) -> JSONResponse:
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        return JSONResponse({"error": {"code": "missing_file",
                                       "message": "multipart field 'file' required"}}, 422)
    data = await upload.read()
    try:
        asset = file_store.ingest_design(data, upload.filename or "design.png")
    except file_store.IngestError as e:
        return JSONResponse({"error": {"code": e.code, "message": str(e)}}, 422)
    return JSONResponse({
        "design_id": asset.design_id, "width": asset.width, "height": asset.height,
        "has_alpha": asset.has_alpha, "text_heavy": asset.text_heavy,
    })


@mcp.custom_route("/files/{file_id}", methods=["GET"])
async def serve_file(request: Request) -> FileResponse | JSONResponse:
    path = file_store.resolve(request.path_params["file_id"])
    if path is None:
        return JSONResponse({"error": {"code": "not_found", "message": "no such file"}}, 404)
    return FileResponse(path, media_type="image/png")


@mcp.custom_route("/jobs/{job_id}/abort", methods=["POST"])
async def abort_job(request: Request) -> JSONResponse:
    jobs.abort(request.path_params["job_id"])
    return JSONResponse({"ok": True})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def run() -> None:
    file_store.init()
    mcp.run(
        transport="http",
        host=os.environ.get("MCP_BIND_HOST", "127.0.0.1"),
        port=int(os.environ.get("MCP_PORT", "8100")),
    )


if __name__ == "__main__":
    run()

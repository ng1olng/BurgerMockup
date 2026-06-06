"""burgermockup-mcp-server — assembly.

5 MCP tools over streamable HTTP plus three HTTP side-channels. Locally it binds
127.0.0.1 (loopback only). On a public host, set MCP_AUTH_TOKEN and the Bearer gate
(server/auth_middleware.py) guards /mcp + the mutation routes; /health and /files stay
open. Side-channels:
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
from server.tools.mockup_tools import generate_mockups, refine_mockups

mcp = FastMCP("burgermockup")
# Logs every MCP request/tool call with args. Payloads here are IDs and scene
# specs only — never secrets or image bytes — so they are safe on the console.
mcp.add_middleware(LoggingMiddleware(include_payloads=True))

mcp.tool(register_design)
mcp.tool(match_product)
mcp.tool(generate_mockups)
mcp.tool(refine_mockups)
mcp.tool(export_listing)


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
    # http_app() returns the Starlette ASGI app (serves /mcp + the custom routes) so we can
    # layer the Bearer gate and bind the platform-injected port ourselves. mcp.run() can't do
    # either: it owns port selection and exposes no hook for request-level auth.
    from server.auth_middleware import BearerGateMiddleware

    app = mcp.http_app()
    app.add_middleware(BearerGateMiddleware)

    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("MCP_BIND_HOST", "127.0.0.1"),
        # Railway (and most PaaS) inject PORT; compose/dev fall back to MCP_PORT then 8100.
        port=int(os.environ.get("PORT") or os.environ.get("MCP_PORT", "8100")),
    )


if __name__ == "__main__":
    run()

"""Transport spike server: proves (a) per-iteration progress notifications are
delivered over streamable HTTP, (b) a host-side abort flag stops a running tool
loop between iterations. MCP-level cancellation is NOT used anywhere — it is
not reliably supported by the server framework (fastmcp #1305)."""

import asyncio
import json

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP("spike")

_aborted: set[str] = set()


@mcp.custom_route("/jobs/{job_id}/abort", methods=["POST"])
async def abort_job(request: Request) -> JSONResponse:
    _aborted.add(request.path_params["job_id"])
    return JSONResponse({"ok": True})


@mcp.tool
async def slow_job(job_id: str, n: int, ctx: Context) -> dict:
    """Loop n iterations (1s each), reporting progress; stop if job aborted."""
    done = 0
    for i in range(n):
        if job_id in _aborted:
            break
        await asyncio.sleep(1)
        done += 1
        await ctx.report_progress(
            progress=done,
            total=n,
            message=json.dumps({"event": "iter_done", "i": done}),
        )
    return {"job_id": job_id, "completed": done, "aborted": job_id in _aborted}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8765)

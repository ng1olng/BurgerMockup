"""Transport spike client. Asserts over REAL streamable HTTP (not in-process):
1. all N progress notifications arrive at the client's progress handler;
2. POST /jobs/{id}/abort stops the server loop between iterations.
Exit code 0 = spike passed."""

import asyncio
import json
import sys

import httpx
from fastmcp import Client

URL = "http://127.0.0.1:8765/mcp"


async def main() -> None:
    events: list[dict] = []

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        events.append(json.loads(message) if message else {"progress": progress})

    async with Client(URL) as client:
        tools = await client.list_tools()
        assert any(t.name == "slow_job" for t in tools), f"tools: {[t.name for t in tools]}"

        # --- assertion 1: progress delivery -------------------------------
        res = await client.call_tool(
            "slow_job", {"job_id": "job-a", "n": 3}, progress_handler=on_progress
        )
        out = res.data
        assert out["completed"] == 3, out
        assert len(events) == 3, f"expected 3 progress events, got {len(events)}: {events}"
        assert events[-1] == {"event": "iter_done", "i": 3}, events

        # --- assertion 2: abort stops the loop -----------------------------
        events.clear()

        async def abort_soon() -> None:
            await asyncio.sleep(1.5)  # let ~2 iterations start
            async with httpx.AsyncClient() as http:
                r = await http.post("http://127.0.0.1:8765/jobs/job-b/abort")
                assert r.status_code == 200

        call = client.call_tool(
            "slow_job", {"job_id": "job-b", "n": 5}, progress_handler=on_progress
        )
        res2, _ = await asyncio.gather(call, abort_soon())
        out2 = res2.data
        assert out2["aborted"] is True, out2
        assert out2["completed"] < 5, f"abort did not stop the loop: {out2}"

    print(f"SPIKE PASS: progress 3/3 delivered; abort stopped loop at "
          f"{out2['completed']}/5 iterations")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print(f"SPIKE FAIL: {e}")
        sys.exit(1)

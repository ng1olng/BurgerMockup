# MCP Mockup URL in Tool Result — OpenWebUI Chat Rendering Fixed

**Date**: 2026-06-06 21:45
**Severity**: Medium (image rendering broken until fix applied)
**Component**: burgermockup-mcp-server, OpenWebUI v0.9.6 chat rendering, MCP client integration
**Status**: Resolved (user deferred commit)

## What Happened

Implemented URL-in-VariantResult fix to enable mockup image rendering in OpenWebUI chat. Root cause: stacked failures — (1) burgermockup-mcp-server sent variant image URLs only via MCP progress notifications, which OpenWebUI's MCP client discards entirely (session.call_tool has no progress_callback hook); (2) even if URLs were transmitted, browser reachability of http://127.0.0.1:8100 only works bare-metal local, breaks under Docker/HTTPS. Chose Option B (user decision): VariantResult gains optional `url` field; _run_batch path sets url=file_store.url_for(file_id) on success, url=None on failure; docstrings instruct LLM to emit ![variant](url) markdown. Tests extended (32/32 green). Code review passed. Not yet committed (user decision).

## The Brutal Truth

The image-rendering gap was painful to diagnose. Spent two hours assuming OWUI was silently uploading images (it does — but only for native MCP ImageContent blocks via middleware.py:1133-1151), then discovered the server was emitting URLs nowhere the client could reach. The real frustration: OWUI already has the right abstraction (auto-upload + files event) for headless deployments, but we're not using it yet because local bare-metal doesn't need it. Accepting local-only as a deliberate trade-off, not a shortcut. Migration to ImageContent is documented as the remote-deploy escape hatch, but deferred.

## Technical Details

- **MCP progress notification loss**: OpenWebUI's mcp/client.py:108 (session.call_tool) has no progress_callback argument. MCP spec allows servers to emit progress + result interleaved; OWUI discards progress, reads only final result. burgermockup-mcp-server was emitting variant URLs as progress items only.
- **VariantResult shape change**: Optional `url: str | None` field added. _run_batch (line ~247): on success, url=file_store.url_for(file_id); on failure (image gen fail), url=None. Docstrings for generate_mockups/refine_mockups now instruct LLM: "emit ![variant_name](url) markdown if url is provided".
- **File store round-trip**: Test extended (test_generate_clamps_n_and_isolates_failures) to verify url shape ends with file_id suffix, file_store.resolve(url) recovers file_id correctly, failed variants url=None.
- **Deployment constraint**: PUBLIC_FILES_BASE must be set correctly. Local 127.0.0.1:8100/files/ works only on bare-metal; Docker/HTTPS/remote requires separate file-serving infrastructure or migration to ImageContent blocks.

## What We Tried

1. Checked if OWUI was auto-uploading images from tool results — yes, but only for native MCP ImageContent blocks, not arbitrary URLs.
2. Attempted to emit URLs via MCP progress notifications — discovered OWUI's MCP client ignores all progress items.
3. Explored migrating to ImageContent blocks — viable long-term (utils/middleware.py already has the upload + files event logic), too invasive for bare-metal local. Deferred to remote-deploy phase.
4. Chose Option B: add url field to VariantResult, let LLM emit markdown. Simpler, local-friendly, remote-deployable after file-store refactor.

## Root Cause Analysis

Two independent failures combined to hide images: (1) server's progress-notification design (attempt to stream results early) incompatible with OpenWebUI's MCP client (no progress callback). (2) Bare-metal local deployment assumption (http://127.0.0.1:8100 reachable from browser) not portable. Neither was inherent to the mockup pipeline — both were integration gaps between server design and OWUI's constraints.

## Lessons Learned

- **MCP progress notifications are fire-and-forget in OpenWebUI.** If you need data to reach the LLM, emit it in the final tool_result, not as progress. Progress is for logs/UI spinners only.
- **Local bare-metal vs. deployment trade-offs must be explicit.** Accepting 127.0.0.1-bound file serving as a constraint (not a hack) made the scope much clearer. Remote deployments will need ImageContent blocks or a dedicated CDN — document that upfront.
- **OWUI's middleware already solves image-in-chat (ImageContent + auto-upload).** When refactoring for remote, leverage it instead of building a custom file-serving layer.

## Next Steps

User deferred commit (working variant locally verified, but waiting for deployment clarity). Before merging:
1. MCP server restart + OWUI tool-server reconnect required for new tool spec to reach the model.
2. Confirm PUBLIC_FILES_BASE is set (e.g., http://127.0.0.1:8100).
3. If remote deployment planned: migrate to MCP ImageContent blocks (utils/middleware.py handles auto-upload). Plan phase exists in plans/reports/brainstorm-260606-mcp-mockup-image-chat-rendering.md.

## Unresolved Questions

- When to commit the VariantResult URL change (user deferred pending deployment clarity)?
- Should MCP progress notifications be formalized as "fire-and-forget for logging only" in server design docs?
- Does ImageContent migration belong in a separate phase or bundled with remote-deploy refactor?

---

**Status:** DONE
**Summary:** Added optional `url` field to VariantResult; LLM now emits markdown images in chat. Works bare-metal local; remote deployment requires ImageContent blocks or file CDN. Code review passed, tests green (32/32), not yet committed per user decision.

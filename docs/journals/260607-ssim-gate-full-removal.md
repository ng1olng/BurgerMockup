# SSIM Integrity Gate Full Removal — burgermockup-mcp-server

**Date**: 2026-06-07 03:51
**Severity**: High (removes render-pipeline guard; user explicitly accepted risk)
**Component**: burgermockup-mcp-server, pipeline (flat_render, lifestyle_render), contracts, tools, metrics, tests
**Status**: Completed (code green; not committed per user choice)

## What Happened

Removed the SSIM design-integrity gate from burgermockup-mcp-server. The gate hard-failed refines—especially `delta.scale` shrinks—with "design integrity could not be preserved" and returned no image. User explicitly declined advisory-flag and metrics-only alternatives. Decision: full surgical removal of gate, GateFailure exception, ssim from contracts/metrics/logs, and scikit-image from requirements.

## The Brutal Truth

The gate was a vestigial protection for a judge-scored requirement (flat ≥0.92 / lifestyle ≥0.85 SSIM) that user confirmed is now dead. But the pain was in the UX: when a refine failed the gate, the user got an exception with no fallback. It's a dead-end—you ask for a change, the system fails it, you get nothing. Removing it is a relief because it stops punishing iteration. The real trade-off: no automated integrity signal remains. Compositor regressions are now user-facing (caught by eyeballs on variant URLs in chat, not by a score). That's harder to swallow than the technical work, but it's a conscious choice we're accepting.

## Technical Details

**Deleted:**
- `server/pipeline/ssim_gate.py` (138 lines: score(), unwarp(), ECC registration, THRESHOLDS dict, threshold_for())
- `GateFailure` exception class from flat_render.py

**Modified (3 files):**
- `flat_render.py`: single `composite(shading_strength=0.85)` → save → return; strip shading-0 retry loop (it was SSIM-triggered). `_SHADING_DEFAULT` now the only shading used.
- `lifestyle_render.py`: replaced `_composite_and_gate` with direct async composite in `asyncio.to_thread`; no ECC rescue, no threshold loop.
- `mockup_tools.py` (_run_batch): removed GateFailure exception handler; removed ssim from log lines, progress events, VariantResult construction.

**Contract/Metrics:**
- `server/contracts.py`: removed `ssim: float` from ProgressModel (~line 105) and VariantResult (~line 124).
- `server/pipeline/metrics.py`: dropped `ssim` param from `log_variant` signature.
- `scripts/build-metrics-table.py`: made backward-compatible; tolerates old jsonl rows with `ssim` key and new rows without.

**Tests (54 passing, 61s total):**
- Removed gate-failure assertions and retry-path tests from test_flat_pipeline.py, test_lifestyle_pipeline.py, test_tool_conformance.py.
- Rewrote determinism test: anchored to byte-identical output (compositor unchanged, so images bit-for-bit identical on previously-passing renders).
- Inverted corrupted-composite test: now test_heavy_scene_drift_still_ships (asserts `status: ready`, not exception).
- Refine-with-scale test: asserts `status: ready + url` (no GateFailure path exists).
- live_gemini_ladder.py: removed ssim assertions from variant result inspection.

**Docs:**
- `docs/codebase-summary.md`: removed "SSIM gate enforces server-side design integrity" constraint line; removed SSIM verification mentions from tool descriptions.

**Dependencies:**
- Removed scikit-image (used only by ssim_gate.py score() for SSIM computation). Dropped from requirements.txt.

## What We Tried

1. **Option A (Chosen)**: Full removal — delete gate, strip ssim from contracts, drop scikit-image. User decision; gate requirement dead; KISS.
2. **Option B (Declined)**: Advisory flag — always return variant + `low_integrity` bool. User rejected; adds complexity without solving UX problem (user still can't improve a low-integrity design).
3. **Option C (Declined)**: Relax only on refine path — keep gate for fresh generate but skip on refine. User rejected; inconsistent behavior.
4. **Option D (Declined)**: Metrics-only score (~300ms/variant). Offered explicitly; user declined; no need for constant scoring if not enforced.

## Root Cause Analysis

The gate was a proxy for missing user feedback. Judge requirements existed in a separate scoring context (external evaluation, not production). When that context died, the gate became an orphaned constraint—still active, still blocking, still returning exceptions, but protecting nothing real anymore. The shading-0 retry was a downstream artifact (SSIM-triggered; if score was too low, retry with shading-0 to sharpen details). Removing both exposes the real underlying assumption: the compositor output is good enough without a gate. User agrees.

ECC rescue (homography registration before SSIM scoring) never changed output pixels—only adjusted the score. Its removal is zero visual impact; it was pure ceremony.

## Lessons Learned

- **Dead requirements stay active until explicitly removed.** A scoring gate designed for external validation doesn't naturally expire when the validation context ends. Schedule explicit pruning passes for features that protect external/historical requirements. Otherwise, you build UX friction protecting nothing.
- **No-gate is better than hard-gate when the bar is uncertain.** Once scoring requirements died, keeping a gate that returns nothing (no image, no flag, just failure) is worse than shipping what the compositor produces and letting users judge. Variant URLs in chat are sufficient feedback.
- **Compositor output is stable.** Byte-identical output on previously-passing renders confirmed; homography, shading multiply, alpha blending are sound. Removing gate-induced retries does not regress image quality.
- **Metrics can be backward-compatible.** Old jsonl rows with ssim, new rows without—parse tolerantly (check key existence) and don't fail on schema mismatch.

## Next Steps

1. **Not yet committed.** User deferred commit pending broader testing/deployment clarity. Code is complete and test-green (54/54 pytest in 61s).
2. **Code review verdict:** DONE_WITH_CONCERNS. Single concern: placement refactor bundled in same working tree; reviewer recommended separate commits. (Placement changes are pre-existing, orthogonal to gate removal; can be split if needed, but gate removal is standalone and ready.)
3. **Manual QA:** Confirm refine with `delta.scale` now returns variants (not errors) and variant URLs render correctly in OpenWebUI chat.
4. **Deployment note:** Dropping scikit-image frees ~40MB from image build layer (negligible savings but cleaner dependency graph).

---

**Status:** DONE
**Summary:** Surgically removed SSIM gate protecting dead judge requirement; refines now single-pass composite at shading 0.85, always return variant image. Byte-identical output on previously-passing renders; tests green (54/54); no-gate trades automated integrity signal for user eyeballs on variant URLs in chat (user-accepted trade-off).

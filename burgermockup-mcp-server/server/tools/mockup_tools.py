"""generate_mockups / refine_mockups — MOCK pipeline bodies.

`_render_variant` is the swap point where the real compositor + SSIM gate and
the scene generator replace the mock; tool signatures, validation, progress
protocol, abort behavior, and per-variant error isolation are frozen and do
not change with the swap.

Invariants enforced in this layer (not trusted to the LLM):
- n clamped to MAX_VARIANTS; negative constraints injected server-side
- abort set checked between variants (host-controlled job abort)
- one variant's failure never kills the batch
- compact results: detailed metrics go to the UI via progress notifications;
  ready variants also carry their image url in the result, because host MCP
  clients (e.g. Open WebUI) drop progress notifications and the result is the
  only channel that reliably reaches the model
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastmcp import Context

from server import jobs
from server.catalog import store
from server.contracts import MAX_VARIANTS, SceneSpec, VariantResult, tool_error
from server.pipeline import scene_cache, scene_gen
from server.pipeline.flat_render import GateFailure, render_flat
from server.pipeline.lifestyle_render import render_lifestyle
from server.pipeline.scene_gen import SceneGenError
from server.storage import file_store

# Test pacing hooks: `__slow__` simulates a long generation (stress/abort
# tests); `__fail__` forces a variant failure (isolation tests).
_MOCK_SLOW_DELAY_S = 5.0

_log = logging.getLogger(__name__)


async def _report(ctx: Context, i: int, n: int, event: str, **payload) -> None:
    await ctx.report_progress(
        progress=i, total=n, message=json.dumps({"event": event, **payload})
    )


async def _render_variant(design_id: str, product_id: str, spec: dict, scene_id: str,
                          design_scale: float = 1.0) -> dict:
    """Render one variant; returns {file_id, ssim, cost_usd}.

    Lifestyle (scene requested + scene model configured, or a cached scene
    exists for this scene_id): generated/cached blank scene + ECC-registered
    gate. Otherwise flat: the scene is the upscaled catalog base. CV work runs
    in a thread so progress/heartbeats keep flowing."""
    design_path = file_store.resolve(design_id)
    product = store.get_product(product_id)
    base_path = store.base_image_path(product_id)
    area = next((a for a in product.print_areas if a.quad), None)
    quad = [(p.x, p.y) for p in area.quad]
    meta = file_store.design_meta(design_id) or {}
    label = spec.get("niche") or spec.get("setting") or "flat"

    wants_scene = bool(spec.get("niche") or spec.get("setting"))
    has_cached_scene = scene_cache.load_scene(scene_id) is not None
    if has_cached_scene or (wants_scene and scene_gen.available()):
        _log.info("path=lifestyle scene_id=%s cached=%s label=%s",
                  scene_id, has_cached_scene, label)
        try:
            return await render_lifestyle(
                design_path, base_path, quad, spec, scene_id,
                garment_type=product.type, text_heavy=meta.get("text_heavy", False),
                prompt_label=label, mockup_id=scene_id, design_scale=design_scale)
        except SceneGenError:
            if has_cached_scene:
                raise  # a cached-scene refine must never silently change scenes
            # Scene model configured but failing (quota/outage): a flat mockup
            # beats an error wall — degrade per variant, flagged in the result.
            _log.warning("scene generation failed; degrading to flat "
                         "(scene_id=%s label=%s)", scene_id, label)
    # Flat path: no scene model, or scene generation degraded (cost 0,
    # judge-scored SSIM still enforced).
    _log.info("path=flat scene_id=%s label=%s", scene_id, label)
    flat = await asyncio.to_thread(
        render_flat, design_path, base_path, quad,
        text_heavy=meta.get("text_heavy", False),
        prompt=label, mockup_id=scene_id, design_scale=design_scale)
    if wants_scene:
        flat["degraded"] = True  # asked for a scene, delivered flat
    return flat


async def _run_batch(
    ctx: Context, job_id: str, design_id: str, product_id: str,
    variant_plans: list[dict], design_scale: float = 1.0,
) -> dict:
    results: list[VariantResult] = []
    n = len(variant_plans)
    for i, plan in enumerate(variant_plans, start=1):
        if jobs.is_aborted(job_id):
            _log.info("job %s aborted after %d/%d variants", job_id, i - 1, n)
            break
        vid, scene_id, spec = plan["variant_id"], plan["scene_id"], plan["spec"]
        label = spec.get("niche") or spec.get("setting") or product_id
        _log.info("variant %s (%d/%d) start label=%s", vid, i, n, label)
        await _report(ctx, i, n, "variant_started", variant_id=vid, scene_label=label)
        t0 = time.time()
        try:
            if spec.get("niche") == "__slow__":
                await asyncio.sleep(_MOCK_SLOW_DELAY_S)
            if spec.get("niche") == "__fail__":  # deterministic failure path for host tests
                raise RuntimeError("mock failure")
            r = await _render_variant(design_id, product_id, spec, scene_id,
                                      design_scale=design_scale)
            _log.info("variant %s ready ssim=%.4f latency=%dms cost=$%.3f degraded=%s",
                      vid, r["ssim"], int((time.time() - t0) * 1000),
                      r["cost_usd"], r.get("degraded", False))
            await _report(
                ctx, i, n, "variant_ready",
                variant_id=vid, url=file_store.url_for(r["file_id"]),
                ssim=r["ssim"], latency_ms=int((time.time() - t0) * 1000),
                cost_usd=r["cost_usd"], degraded=r.get("degraded", False),
            )
            results.append(VariantResult(variant_id=vid, scene_id=scene_id,
                                         status="ready", ssim=r["ssim"],
                                         url=file_store.url_for(r["file_id"]),
                                         degraded=r.get("degraded", False)))
        except GateFailure as e:
            # GateFailure messages carry the failing score vs threshold.
            _log.warning("variant %s gate failure: %s", vid, e)
            await _report(ctx, i, n, "variant_failed", variant_id=vid,
                          message="design integrity could not be preserved for this variant")
            results.append(VariantResult(variant_id=vid, scene_id=scene_id, status="failed"))
        except SceneGenError as e:
            # SceneGenError messages are fixed strings by construction.
            _log.warning("variant %s scene generation failed: %s", vid, e)
            await _report(ctx, i, n, "variant_failed", variant_id=vid, message=str(e))
            results.append(VariantResult(variant_id=vid, scene_id=scene_id, status="failed"))
        except Exception:
            # Fixed-string message only — internal errors are never echoed to
            # the client; the full traceback is logged server-side instead.
            _log.exception("variant %s failed (design=%s product=%s label=%s)",
                           vid, design_id, product_id, label)
            await _report(ctx, i, n, "variant_failed", variant_id=vid,
                          message="variant generation failed")
            results.append(VariantResult(variant_id=vid, scene_id=scene_id, status="failed"))
    jobs.clear(job_id)
    return {"variants": [r.model_dump() for r in results]}


async def generate_mockups(
    job_id: str, design_id: str, product_id: str,
    scene_specs: list[dict], n: int, ctx: Context,
) -> dict:
    """Generate n mockup variants of a registered design on a catalog product.
    Streams per-variant progress; the design itself is never altered by AI.
    Each ready variant includes a `url`; display it to the user as a markdown
    image: ![variant](url)."""
    _log.info("generate_mockups job=%s design=%s product=%s n=%s specs=%d",
              job_id, design_id, product_id, n, len(scene_specs or []))
    if not file_store.resolve(design_id):
        return tool_error("design_not_found", "design_id is not registered")
    product = store.get_product(product_id)
    if product is None:
        return tool_error("product_not_found", "product_id is not in the catalog")
    if not any(a.quad for a in product.print_areas):
        return tool_error("no_print_area", "this product has no annotated print area yet")

    try:
        n = max(1, min(int(n), MAX_VARIANTS))
    except (TypeError, ValueError):
        return tool_error("invalid_n", "n must be an integer")
    specs = [SceneSpec(**{k: v for k, v in (s or {}).items()
                          if k in SceneSpec.model_fields}).with_constraints()
             for s in (scene_specs or [{}])]
    plans = [
        {"variant_id": str(uuid.uuid4()), "scene_id": str(uuid.uuid4()),
         "spec": specs[i % len(specs)]}
        for i in range(n)
    ]
    return await _run_batch(ctx, job_id, design_id, product_id, plans)


async def refine_mockups(
    job_id: str, design_id: str, product_id: str,
    variants: list[dict], delta: dict, ctx: Context,
) -> dict:
    """Refine existing variants. delta.type: design (reuse scenes, no image-model
    call) | scene (regenerate scenes) | product (new garment). delta.change:
    niche name or free-form scene description for scene delta; omit for a fresh
    default scene. target_ordinal (1-based) limits the refine to one variant.
    delta.scale (0.3–1.6) resizes the printed design (1.0 = unchanged). Each
    ready variant includes a `url`; display it as a markdown image: ![v](url)."""
    _log.info("refine_mockups job=%s design=%s product=%s delta=%s variants=%d",
              job_id, design_id, product_id, delta.get("type"), len(variants or []))
    if delta.get("type") not in ("design", "scene", "product"):
        return tool_error("invalid_delta", "delta.type must be design, scene, or product")
    if not variants:
        return tool_error("no_variants", "variants list is empty — generate first")
    try:
        design_scale = min(max(float(delta.get("scale") or 1.0), 0.3), 1.6)
    except (TypeError, ValueError):
        return tool_error("invalid_scale", "delta.scale must be a number")

    ordinal = delta.get("target_ordinal")
    targets = list(variants)
    if ordinal is not None:
        try:
            ordinal = int(ordinal)
        except (TypeError, ValueError):
            return tool_error("invalid_ordinal", "target_ordinal must be an integer")
        if not (1 <= ordinal <= len(variants)):
            return tool_error("ordinal_out_of_range",
                              f"target_ordinal must be between 1 and {len(variants)}")
        targets = [variants[ordinal - 1]]

    # Design delta must not look like a scene request: spec stays empty so a
    # cache miss recomposites on the flat base instead of calling the model.
    # Scene delta: put change in niche so wants_scene=True even when change is
    # empty — empty change defaults to "cafe" so the lifestyle path runs.
    change = delta.get("change") or ""
    spec = (SceneSpec().with_constraints() if delta["type"] == "design"
            else SceneSpec(niche=change or "cafe").with_constraints())
    plans = [
        {"variant_id": v["variant_id"],
         # design delta reuses the existing scene; scene/product mint a new one
         "scene_id": v["scene_id"] if delta["type"] == "design" else str(uuid.uuid4()),
         "spec": spec}
        for v in targets
    ]
    return await _run_batch(ctx, job_id, design_id, product_id, plans,
                            design_scale=design_scale)

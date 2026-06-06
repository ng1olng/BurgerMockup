"""generate_mockups / refine_mockups — MOCK pipeline bodies.

`_render_variant` is the swap point where the real compositor and the scene
generator replace the mock; tool signatures, validation, progress protocol,
abort behavior, and per-variant error isolation are frozen and do not change
with the swap.

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

import numpy as np
from fastmcp import Context
from PIL import Image

from server import jobs
from server.catalog import store
from server.contracts import MAX_VARIANTS, SceneSpec, VariantResult, tool_error
from server.pipeline import scene_cache, scene_gen
from server.pipeline.flat_render import render_flat
from server.pipeline.lifestyle_render import render_lifestyle
from server.pipeline.placement import PLACEMENTS, compute_quad, placement_ladder
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
                          design_scale: float = 1.0,
                          placement: str = "center") -> dict:
    """Render one variant; returns {file_id, cost_usd}.

    Lifestyle (scene requested + scene model configured, or a cached scene
    exists for this scene_id): generated/cached blank scene. Otherwise flat:
    the scene is the upscaled catalog base. CV work runs in a thread so
    progress/heartbeats keep flowing."""
    design_path = file_store.resolve(design_id)
    product = store.get_product(product_id)
    base_path = store.base_image_path(product_id)
    # Print quad computed from the base's alpha silhouette (the public API has
    # no print-area data) — deterministic, so flat re-renders with the same
    # placement reproduce the same region. Cached scenes keep their stored quad.
    base_rgba = np.array(Image.open(base_path).convert("RGBA"))
    quad = compute_quad(base_rgba, product.type, placement)
    label = spec.get("niche") or spec.get("setting") or "flat"

    wants_scene = bool(spec.get("niche") or spec.get("setting"))
    has_cached_scene = scene_cache.load_scene(scene_id) is not None
    if has_cached_scene or (wants_scene and scene_gen.available()):
        _log.info("path=lifestyle scene_id=%s cached=%s label=%s",
                  scene_id, has_cached_scene, label)
        try:
            return await render_lifestyle(
                design_path, base_path, quad, spec, scene_id,
                garment_type=product.type, prompt_label=label,
                mockup_id=scene_id, design_scale=design_scale)
        except SceneGenError:
            if has_cached_scene:
                raise  # a cached-scene refine must never silently change scenes
            # Scene model configured but failing (quota/outage): a flat mockup
            # beats an error wall — degrade per variant, flagged in the result.
            _log.warning("scene generation failed; degrading to flat "
                         "(scene_id=%s label=%s)", scene_id, label)
    # Flat path: no scene model, or scene generation degraded (cost 0).
    _log.info("path=flat scene_id=%s label=%s", scene_id, label)
    flat = await asyncio.to_thread(
        render_flat, design_path, base_path, quad,
        prompt=label, mockup_id=scene_id, design_scale=design_scale)
    if wants_scene:
        flat["degraded"] = True  # asked for a scene, delivered flat
    return flat


async def _run_batch(
    ctx: Context, job_id: str, design_id: str, product_id: str,
    variant_plans: list[dict],
) -> dict:
    # Placement/design_scale live on each plan (flat batches vary them per
    # variant via the variety ladder); results echo them so the host can pass
    # them back on refine — the server is stateless.
    results: list[VariantResult] = []
    n = len(variant_plans)
    for i, plan in enumerate(variant_plans, start=1):
        if jobs.is_aborted(job_id):
            _log.info("job %s aborted after %d/%d variants", job_id, i - 1, n)
            break
        vid, scene_id, spec = plan["variant_id"], plan["scene_id"], plan["spec"]
        v_placement = plan.get("placement", "center")
        v_scale = plan.get("design_scale", 1.0)
        label = spec.get("niche") or spec.get("setting") or product_id
        _log.info("variant %s (%d/%d) start label=%s placement=%s scale=%.2f",
                  vid, i, n, label, v_placement, v_scale)
        await _report(ctx, i, n, "variant_started", variant_id=vid, scene_label=label)
        t0 = time.time()
        try:
            if spec.get("niche") == "__slow__":
                await asyncio.sleep(_MOCK_SLOW_DELAY_S)
            if spec.get("niche") == "__fail__":  # deterministic failure path for host tests
                raise RuntimeError("mock failure")
            r = await _render_variant(design_id, product_id, spec, scene_id,
                                      design_scale=v_scale,
                                      placement=v_placement)
            _log.info("variant %s ready latency=%dms cost=$%.3f degraded=%s",
                      vid, int((time.time() - t0) * 1000),
                      r["cost_usd"], r.get("degraded", False))
            await _report(
                ctx, i, n, "variant_ready",
                variant_id=vid, url=file_store.url_for(r["file_id"]),
                latency_ms=int((time.time() - t0) * 1000),
                cost_usd=r["cost_usd"], degraded=r.get("degraded", False),
                placement=v_placement, design_scale=v_scale,
            )
            results.append(VariantResult(variant_id=vid, scene_id=scene_id,
                                         status="ready",
                                         url=file_store.url_for(r["file_id"]),
                                         degraded=r.get("degraded", False),
                                         placement=v_placement,
                                         design_scale=v_scale))
        except SceneGenError as e:
            # SceneGenError messages are fixed strings by construction.
            _log.warning("variant %s scene generation failed: %s", vid, e)
            await _report(ctx, i, n, "variant_failed", variant_id=vid, message=str(e))
            results.append(VariantResult(variant_id=vid, scene_id=scene_id,
                                         status="failed",
                                         placement=v_placement,
                                         design_scale=v_scale))
        except Exception:
            # Fixed-string message only — internal errors are never echoed to
            # the client; the full traceback is logged server-side instead.
            _log.exception("variant %s failed (design=%s product=%s label=%s)",
                           vid, design_id, product_id, label)
            await _report(ctx, i, n, "variant_failed", variant_id=vid,
                          message="variant generation failed")
            results.append(VariantResult(variant_id=vid, scene_id=scene_id,
                                         status="failed",
                                         placement=v_placement,
                                         design_scale=v_scale))
    jobs.clear(job_id)
    return {"variants": [r.model_dump() for r in results]}


async def generate_mockups(
    job_id: str, design_id: str, product_id: str,
    scene_specs: list[dict], ctx: Context, n: int = 1,
    placement: str = "center",
) -> dict:
    """Generate mockup variants of a registered design on a catalog product.
    `n` defaults to 1 — pass n>1 ONLY when the user explicitly asks for a
    number of images ("give me 5 mockups" -> n=5). Batches without a scene
    automatically vary placement/scale per variant so the images differ.
    Streams per-variant progress; the design itself is never altered by AI.
    `placement` positions the design on the garment: center (default), chest,
    left-chest, right-chest, top, bottom, full-front — map the user's wording
    (VN or EN, e.g. "ngực trái" -> left-chest) to one of these values.
    Each ready variant includes a `url` (display it to the user as a markdown
    image: ![variant](url)) plus the `placement`/`design_scale` it was
    rendered with — pass those back unchanged when refining that variant."""
    _log.info("generate_mockups job=%s design=%s product=%s n=%s specs=%d placement=%s",
              job_id, design_id, product_id, n, len(scene_specs or []), placement)
    if not file_store.resolve(design_id):
        return tool_error("design_not_found", "design_id is not registered")
    product = store.get_product(product_id)
    if product is None:
        return tool_error("product_not_found", "product_id is not in the catalog")
    if store.base_image_path(product_id) is None:
        return tool_error("no_base_image", "this product has no base image asset yet")
    if placement not in PLACEMENTS:
        return tool_error("invalid_placement",
                          "placement must be one of: " + ", ".join(sorted(PLACEMENTS)))

    try:
        n = max(1, min(int(n), MAX_VARIANTS))
    except (TypeError, ValueError):
        return tool_error("invalid_n", "n must be an integer")
    specs = [SceneSpec(**{k: v for k, v in (s or {}).items()
                          if k in SceneSpec.model_fields}).with_constraints()
             for s in (scene_specs or [{}])]
    # Flat batches (no scene anywhere) would render n identical images — the
    # quad is deterministic — so they walk the variety ladder instead. Scene
    # batches keep the requested placement: each variant already differs via
    # its own generated scene.
    wants_scene = any(s.get("niche") or s.get("setting") for s in specs)
    combos = (placement_ladder(placement, n) if n > 1 and not wants_scene
              else [(placement, 1.0)] * n)
    plans = [
        {"variant_id": str(uuid.uuid4()), "scene_id": str(uuid.uuid4()),
         "spec": specs[i % len(specs)],
         "placement": combos[i][0], "design_scale": combos[i][1]}
        for i in range(n)
    ]
    return await _run_batch(ctx, job_id, design_id, product_id, plans)


async def refine_mockups(
    job_id: str, design_id: str, product_id: str,
    variants: list[dict], delta: dict, ctx: Context,
    placement: str = "center",
) -> dict:
    """Refine existing variants — a refine returns ONE image by default. If
    the user doesn't say which image, pass target_ordinal of the most recent
    variant; omit target_ordinal ONLY when the user explicitly asks to update
    ALL images. delta.type: design (reuse scenes, no image-model call) | scene
    (regenerate scenes) | product (new garment). delta.scale (0.3–1.6) resizes
    the printed design (1.0 = unchanged). Pass each variant's `placement` and
    `design_scale` exactly as generate_mockups returned them (batch variants
    differ); to MOVE the design on a scene variant use delta.type=scene —
    a design delta keeps the cached scene's locked position. Each ready variant
    includes a `url`; display it to the user as a markdown image: ![variant](url)."""
    _log.info("refine_mockups job=%s design=%s product=%s delta=%s variants=%d placement=%s",
              job_id, design_id, product_id, delta.get("type"), len(variants or []),
              placement)
    if delta.get("type") not in ("design", "scene", "product"):
        return tool_error("invalid_delta", "delta.type must be design, scene, or product")
    if store.get_product(product_id) is None:
        return tool_error("product_not_found", "product_id is not in the catalog")
    if store.base_image_path(product_id) is None:
        return tool_error("no_base_image", "this product has no base image asset yet")
    if placement not in PLACEMENTS:
        return tool_error("invalid_placement",
                          "placement must be one of: " + ", ".join(sorted(PLACEMENTS)))
    if not variants:
        return tool_error("no_variants", "variants list is empty — generate first")
    # Explicit delta.scale wins ("make it smaller" overrides history); absent,
    # each variant keeps its own recorded design_scale so an unrelated refine
    # doesn't silently reset the printed size.
    try:
        raw = delta.get("scale")
        delta_scale = None if raw is None else min(max(float(raw), 0.3), 1.6)
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
    spec = (SceneSpec().with_constraints() if delta["type"] == "design"
            else SceneSpec(setting=delta.get("change", "")).with_constraints())
    plans = []
    for v in targets:
        # Batch variants carry their own placement/design_scale (variety
        # ladder); missing fields fall back to the tool-level placement and
        # scale 1.0 — pre-ladder hosts keep today's behavior.
        v_placement = v.get("placement") or placement
        if v_placement not in PLACEMENTS:
            return tool_error("invalid_placement",
                              "placement must be one of: " + ", ".join(sorted(PLACEMENTS)))
        try:
            v_scale = (delta_scale if delta_scale is not None
                       else min(max(float(v.get("design_scale") or 1.0), 0.3), 1.6))
        except (TypeError, ValueError):
            return tool_error("invalid_scale", "variant design_scale must be a number")
        plans.append(
            {"variant_id": v["variant_id"],
             # design delta reuses the existing scene; scene/product mint a new one
             "scene_id": v["scene_id"] if delta["type"] == "design" else str(uuid.uuid4()),
             "spec": spec,
             "placement": v_placement, "design_scale": v_scale})
    return await _run_batch(ctx, job_id, design_id, product_id, plans)

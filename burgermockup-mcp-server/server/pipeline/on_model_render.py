"""On-model render path: composite the design onto the flat garment FIRST,
then have the scene model re-render that exact printed garment worn by a
person. The design pixels pass through the image model exactly once, so the
output is near-exact, not print-exact — callers flag it design_fidelity=
"ai-rendered".

No scene_cache participation: the output has no valid print quad (the design
is baked in), so there is nothing to recomposite later — every refine of an
on-model variant is a full re-run."""

from __future__ import annotations

import time

from PIL import Image

from server.pipeline import metrics, scene_gen
from server.pipeline.flat_render import compose_flat_image
from server.pipeline.prompts import on_model_prompt
from server.storage import file_store


async def render_on_model(design_path: str, base_path: str,
                          quad: list[tuple[float, float]], spec: dict, *,
                          prompt_label: str = "", mockup_id: str = "",
                          design_scale: float = 1.0) -> dict:
    """Returns {file_id, cost_usd}; raises SceneGenError (caller degrades to
    flat, mirroring the lifestyle path)."""
    t0 = time.time()
    flat = compose_flat_image(design_path, base_path, quad,
                              design_scale=design_scale)
    image, cost = await scene_gen.generate_scene(
        on_model_prompt(spec), Image.fromarray(flat))
    file_id, _ = file_store.save_image(image.convert("RGB"))
    metrics.log_variant(mockup_id or file_id, prompt_label, scene_gen.MODEL,
                        int((time.time() - t0) * 1000), cost)
    return {"file_id": file_id, "cost_usd": cost}

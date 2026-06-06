"""Tool I/O models — the product API of the MCP server. The host's agent loop,
the rules-mode router, and external MCP hosts (e.g. Claude Desktop) all build
on these shapes; they are frozen and change additively only.

The server holds NO session state: callers pass design/product/variant context
into each tool call; the host's database is the single session authority.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# Hard cap on variants per call, enforced server-side so a prompt-injected
# "n: 9999" can never fan out unbounded paid generation.
MAX_VARIANTS = 8

# Hard constraints injected into every SceneSpec server-side; NEVER read from
# tool args (compliance + anti-injection).
NEGATIVE_CONSTRAINTS = ["no_real_brands", "no_celebrities"]

# Decoded-pixel ceiling for uploaded images. The 25MB wire cap alone does not
# stop decompression bombs (a small PNG can decode to gigapixels and OOM).
MAX_IMAGE_PIXELS = 40_000_000
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class Point(BaseModel):
    x: float
    y: float


class Color(BaseModel):
    id: str
    name: str
    color_hex: str


class Product(BaseModel):
    """Catalog product. The public API exposes no print-area data; the print
    region is computed from the base image at render time (pipeline/placement)."""

    short_code: str
    name: str
    type: str = "tshirt"
    available_colors: list[Color] = Field(default_factory=list)
    base_url: str = ""
    resolution_default: str = ""


class DesignAsset(BaseModel):
    design_id: str
    path: str  # normalized RGBA on disk (server-internal, never returned raw)
    width: int
    height: int
    has_alpha: bool
    text_heavy: bool = False


class SceneSpec(BaseModel):
    niche: str = ""
    setting: str = ""
    model_persona: str = ""
    lighting: str = ""
    mood: str = ""
    market: str = ""

    def with_constraints(self) -> dict:
        """Serialize with the system-side negative constraints attached."""
        d = self.model_dump()
        d["negative_constraints"] = list(NEGATIVE_CONSTRAINTS)
        return d


class SceneAsset(BaseModel):
    """A persisted BLANK scene (garment + background, design NOT composited).
    Reloading it by scene_id is what keeps design-only refines from silently
    changing a background the seller already approved."""

    scene_id: str
    image_path: str
    garment_type: str = ""
    color: str = ""
    print_quad: list[list[float]] = Field(default_factory=list)
    shading_map_ref: str = ""


class VariantRef(BaseModel):
    """Compact variant reference passed between host and server (refine input).

    `placement`/`design_scale` echo what generate_mockups returned for this
    variant: flat batches vary them per variant (variety ladder), and the
    server is stateless, so the host must round-trip them or a flat refine
    would recompute the wrong quad. Empty/None falls back to the tool-level
    placement param (pre-ladder hosts keep working)."""

    variant_id: str
    scene_id: str
    placement: str = ""
    design_scale: Optional[float] = None


class VariantResult(BaseModel):
    """Compact tool result per variant. Detailed metrics travel via progress
    notifications to the UI; ready variants also carry their image `url` here
    because host MCP clients (e.g. Open WebUI) drop progress notifications, so
    the tool result is the only channel that reliably reaches the model."""

    variant_id: str
    scene_id: str
    status: str  # ready | failed
    # Browser-fetchable image URL (PUBLIC_FILES_BASE + /files/{id}.png);
    # None for failed variants.
    url: Optional[str] = None
    # True when a scene was requested but the variant fell back to the flat
    # path (scene model failing) — consumers must be able to disclose this.
    degraded: bool = False
    # The (placement, design_scale) this variant was rendered with. Flat
    # batches vary these per variant (variety ladder); hosts must pass them
    # back on refine so the variant reproduces its own quad.
    placement: str = ""
    design_scale: float = 1.0


class RefineDelta(BaseModel):
    type: str  # design | scene | product
    change: str = ""
    target_ordinal: Optional[int] = None  # 1-based; None = all variants


class MetricsRow(BaseModel):
    mockup_id: str
    prompt: str
    model: str
    latency_ms: int
    cost_usd: float
    timestamp: str


# Progress-notification payload vocabulary (the `message` field of MCP progress
# notifications, JSON-encoded). The host bridges these 1:1 onto its SSE events
# mockup_started / mockup_ready / error.
PROGRESS_EVENTS = ("variant_started", "variant_ready", "variant_failed")


def tool_error(code: str, message: str) -> dict:
    """Structured tool error. `message` MUST be a fixed string — provider/OS
    error bodies are never echoed (they reach the LLM and the browser)."""
    return {"error": {"code": code, "message": message}}

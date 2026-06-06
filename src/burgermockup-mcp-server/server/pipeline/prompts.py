"""Niche → scene-prompt fragments (VN/EN). The prompt asks for a GARMENT-
PRESERVING edit: the garment's position, scale and perspective must stay as in
the source so the annotated print quad remains valid (residual drift is
corrected by ECC registration at the gate). Negative constraints are appended
unconditionally — they are system policy, not user input."""

from __future__ import annotations

NICHES: dict[str, dict] = {
    "cafe": {"setting": "a cozy specialty coffee shop, warm window light",
             "persona": "a young woman smiling, casual style"},
    "streetwear": {"setting": "an urban street at golden hour, soft bokeh",
                   "persona": "a young man in streetwear stance"},
    "yoga": {"setting": "a bright minimalist yoga studio",
             "persona": "a middle-aged woman in a relaxed pose"},
    "cozy": {"setting": "a warm living room with soft blankets and fairy lights",
             "persona": "a person relaxing on a couch"},
    "picnic": {"setting": "a sunny park picnic with a blanket and basket",
               "persona": "a young woman sitting on the blanket"},
    "flat-lay": {"setting": "a flat-lay on a rustic wooden table with minimal props",
                 "persona": ""},
    "christmas": {"setting": "a festive room with a Christmas tree and warm lights",
                  "persona": "a cheerful person by the tree"},
}

# VN keywords -> canonical niche key
VN_ALIASES = {
    "cà phê": "cafe", "ca phe": "cafe", "quán cafe": "cafe",
    "đường phố": "streetwear", "dạo phố": "streetwear",
    "tập yoga": "yoga",
    "ấm cúng": "cozy",
    "dã ngoại": "picnic", "picnic": "picnic",
    "trải phẳng": "flat-lay",
    "giáng sinh": "christmas", "noel": "christmas",
}

_NEGATIVE = "No real brand logos, no trademarks, no celebrities or real people likenesses."


def resolve_niche(text: str) -> str:
    t = (text or "").lower()
    if t in NICHES:
        return t
    for vn, key in VN_ALIASES.items():
        if vn in t:
            return key
    return t  # free-form setting; used verbatim


def scene_prompt(spec: dict) -> str:
    niche = resolve_niche(spec.get("niche", ""))
    preset = NICHES.get(niche, {})
    setting = spec.get("setting") or preset.get("setting") or niche or "a clean studio"
    persona = spec.get("model_persona") or preset.get("persona", "")
    lighting = spec.get("lighting", "")
    mood = spec.get("mood", "")
    parts = [
        "Edit this product photo into a lifestyle scene.",
        "CRITICAL: keep the garment itself EXACTLY as in the source image — same "
        "position in frame, same scale, same straight-on perspective, same folds. "
        "Only replace the background and add context around it.",
        f"Scene: {setting}.",
    ]
    if persona:
        parts.append(f"Worn naturally by {persona}, garment front fully visible, unobstructed.")
    if lighting:
        parts.append(f"Lighting: {lighting}.")
    if mood:
        parts.append(f"Mood: {mood}.")
    parts.append("Photorealistic, professional product photography, high resolution.")
    parts.append(_NEGATIVE)
    return " ".join(parts)

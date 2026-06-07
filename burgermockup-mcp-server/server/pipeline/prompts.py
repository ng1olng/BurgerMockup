"""Niche → scene-prompt fragments (VN/EN). The prompt asks for a GARMENT-
PRESERVING edit: the garment's position, scale and perspective must stay as in
the source so the annotated print quad remains valid (residual drift is
corrected by ECC registration at the gate). Negative constraints are appended
unconditionally — they are system policy, not user input."""

from __future__ import annotations

NICHES: dict[str, dict] = {
    "cafe": {
        "setting": "a cozy specialty coffee shop, warm window light",
        "persona": "a young woman smiling, casual style",
        "lighting": "soft natural window light",
        "mood": "warm, relaxed",
    },
    "streetwear": {
        "setting": "an urban street at golden hour, soft bokeh",
        "persona": "a young man in streetwear stance",
        "lighting": "golden hour side light",
        "mood": "cool, editorial",
    },
    "yoga": {
        "setting": "a bright minimalist yoga studio",
        "persona": "a middle-aged woman in a relaxed pose",
        "lighting": "soft diffused studio light",
        "mood": "calm, mindful",
    },
    "cozy": {
        "setting": "a warm living room with soft blankets and fairy lights",
        "persona": "a person relaxing on a couch",
        "lighting": "warm ambient indoor glow",
        "mood": "cozy, intimate",
    },
    "picnic": {
        "setting": "a sunny park picnic with a blanket and basket",
        "persona": "a young woman sitting on the blanket",
        "lighting": "bright natural daylight, soft shadows",
        "mood": "bright, cheerful",
    },
    "flat-lay": {
        "setting": "a flat-lay on a rustic wooden table with minimal props",
        "persona": "",
        "lighting": "even overhead light",
        "mood": "clean, product-focused",
    },
    # Three Christmas sub-variants — use directly as niche to get distinct scenes.
    "christmas": {
        "setting": "a festive living room with a glowing Christmas tree and warm fairy lights",
        "persona": "a cheerful young woman by the tree, natural relaxed pose",
        "lighting": "warm candlelight glow, soft bokeh background",
        "mood": "joyful, cozy, editorial",
    },
    "christmas-outdoor": {
        "setting": "a snowy outdoor porch with string lights and pine wreaths at twilight",
        "persona": "a young person in a cozy winter outfit, genuine smile",
        "lighting": "cold blue twilight with warm window spill light",
        "mood": "magical, cinematic, winter evening",
    },
    "christmas-gifting": {
        "setting": "a holiday gift unwrapping scene, wrapped boxes and ribbons on the floor",
        "persona": "an excited young woman opening gifts, sitting cross-legged",
        "lighting": "soft morning light with warm indoor ambient glow",
        "mood": "excited, festive, authentic lifestyle",
    },
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
    "mùa lễ": "christmas", "lễ giáng sinh": "christmas", "mùa noel": "christmas",
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
    # Caller values take precedence over preset defaults.
    setting = spec.get("setting") or preset.get("setting") or niche or "a clean studio"
    persona = spec.get("model_persona") or preset.get("persona", "")
    lighting = spec.get("lighting") or preset.get("lighting", "")
    mood = spec.get("mood") or preset.get("mood", "")
    camera = spec.get("camera", "")
    composition = spec.get("composition", "")
    style = spec.get("style", "")
    film_look = spec.get("film_look", "")
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
    if camera:
        parts.append(f"Camera: {camera}.")
    if composition:
        parts.append(f"Composition: {composition}.")
    if style:
        parts.append(f"Style: {style}.")
    if film_look:
        parts.append(f"Film look: {film_look}.")
    parts.append("Photorealistic, professional product photography, high resolution.")
    parts.append(_NEGATIVE)
    return " ".join(parts)

"""
agents/color_grader.py

ColorGrading agent — LLM picks a preset based on mood, energy, creative direction.
Preset-based: warm, cool, cinematic, vibrant, muted, high_contrast.
"""

import json
import logging
from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)
LLM_MODEL = "llama-3.3-70b-versatile"

COLOR_PRESETS = "warm, cool, cinematic, vibrant, muted, high_contrast, neutral"

GRADING_PROMPT = """You are a colorist for Instagram Reels.

The video director has decided:
  Mood: {overall_mood}
  Energy: {overall_energy}
  Creative direction: {creative_direction}
  Content type: {content_type}

Pick ONE color grading preset. Options: [{presets}]

- warm: golden, inviting (motivational, lifestyle)
- cool: blue tones (tech, calm, educational)
- cinematic: film look, drama (storytelling)
- vibrant: punchy, saturated (energy, hype)
- muted: desaturated, soft (minimal, calm)
- high_contrast: bold, dramatic
- neutral: no grading, pass-through (use only if content is already perfect)

IMPORTANT: Avoid "neutral" — prefer warm, cool, cinematic, or vibrant to add mood. Only use neutral for raw/authentic content that should stay untouched.

Respond ONLY with valid JSON. No markdown.
{{"color_preset": "warm", "reason": "one sentence"}}"""


def suggest_color_grade(edit_plan: dict) -> str:
    """
    Pick a color grading preset from edit_plan mood/energy/creative_direction.
    Returns preset name: warm, cool, cinematic, vibrant, muted, high_contrast, neutral.
    """
    if not has_keys():
        logger.warning("[ColorGrader] No Groq keys — using neutral preset")
        return "neutral"

    clips = edit_plan.get("clips", [{}])
    content_type = clips[0].get("content_type", "talking_head") if clips else "talking_head"

    prompt = GRADING_PROMPT.format(
        overall_mood=edit_plan.get("overall_mood", "motivational"),
        overall_energy=edit_plan.get("overall_energy", "medium"),
        creative_direction=edit_plan.get("creative_direction", "smooth flow"),
        content_type=content_type,
        presets=COLOR_PRESETS,
    )

    valid_presets = {"warm", "cool", "cinematic", "vibrant", "muted", "high_contrast", "neutral"}

    try:
        logger.info("[ColorGrader] Picking color preset...")
        client = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=80,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        preset = (result.get("color_preset") or "neutral").lower().replace(" ", "_")
        if preset not in valid_presets:
            preset = "neutral"
        logger.info(f"[ColorGrader] Preset: {preset} — {result.get('reason', '')[:50]}")
        return preset
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[ColorGrader] Failed: {e} — using neutral")
        return "neutral"

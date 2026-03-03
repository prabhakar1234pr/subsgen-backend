"""
agents/director.py

CrewAI Agent 2 — DirectorAgent
Uses Llama-3.3-70b via Groq to read all per-clip analyses and
produce a structured EditPlan: clip order, pacing, subtitle style,
music search query.
"""

import json
import logging
import os

from groq import Groq

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
LLM_MODEL = "llama-3.3-70b-versatile"

DIRECTOR_PROMPT = """You are a world-class Instagram Reels editor and director.

You have analyzed {n_clips} video clip(s) and received the following per-clip analysis reports:

{analyses_json}

Your job is to produce a complete EditPlan for stitching these clips into ONE viral Instagram Reel.

Rules:
- You must use ALL clips (do not drop any)
- Order them for maximum viewer retention (hook first, then value, then CTA)
- Choose ONE subtitle style that best fits the overall reel (not per-clip)
- Create a specific Pixabay music search query that will find the perfect background track
- Consider energy arc: usually start medium/high, sustain, end with peak or resolution

Respond ONLY with a valid JSON object. No explanation, no markdown, no extra text.

JSON schema:
{{
  "clip_order": [0, 1, 2],
  "overall_mood": "the dominant mood of the whole reel",
  "overall_energy": "low | medium | high",
  "pacing": "slow | normal | fast | dynamic",
  "trim_aggressiveness": "light | moderate | aggressive",
  "subtitle_style": "hormozi | minimal | neon | fire | karaoke | purple",
  "subtitle_style_reason": "one sentence why this style fits",
  "music_search_query": "specific search query for Pixabay music API (e.g. 'upbeat motivational corporate')",
  "music_mood": "motivational | chill | energy | uplifting | cinematic",
  "music_bpm_preference": "slow | medium | fast | any",
  "edit_notes": "2-3 sentences of director notes on how to cut this reel",
  "hook_strategy": "one sentence describing the opening hook approach",
  "reel_title_suggestion": "a punchy 5-8 word reel title or caption idea"
}}"""


def create_edit_plan(clip_analyses: list[dict]) -> dict:
    """
    Take all per-clip VLM analyses and produce a director's EditPlan.
    """
    if not GROQ_API_KEY:
        logger.warning("No GROQ_API_KEY — using default edit plan")
        return _default_edit_plan(clip_analyses)

    client = Groq(api_key=GROQ_API_KEY)

    analyses_json = json.dumps(clip_analyses, indent=2)
    prompt = DIRECTOR_PROMPT.format(
        n_clips=len(clip_analyses),
        analyses_json=analyses_json
    )

    try:
        logger.info(f"Sending {len(clip_analyses)} clip analyses to Director LLM ({LLM_MODEL})...")
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional Instagram Reels director. Always respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=800,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        plan = json.loads(raw)

        # Validate clip_order contains all indices
        expected = list(range(len(clip_analyses)))
        if sorted(plan.get("clip_order", [])) != expected:
            logger.warning("Director returned invalid clip_order — using default order")
            plan["clip_order"] = expected

        logger.info(f"EditPlan: order={plan.get('clip_order')}, style={plan.get('subtitle_style')}, music='{plan.get('music_search_query')}'")
        return plan

    except json.JSONDecodeError as e:
        logger.error(f"Director LLM returned invalid JSON: {e}")
        return _default_edit_plan(clip_analyses)
    except Exception as e:
        logger.error(f"Director LLM error: {e}")
        return _default_edit_plan(clip_analyses)


def _default_edit_plan(clip_analyses: list[dict]) -> dict:
    """Fallback edit plan when LLM unavailable."""
    n = len(clip_analyses)

    # Try to pick subtitle style from most common in analyses
    styles = [a.get("recommended_subtitle_style", "hormozi") for a in clip_analyses]
    subtitle_style = max(set(styles), key=styles.count)

    moods = [a.get("mood", "motivational") for a in clip_analyses]
    mood = max(set(moods), key=moods.count)

    return {
        "clip_order": list(range(n)),
        "overall_mood": mood,
        "overall_energy": "medium",
        "pacing": "normal",
        "trim_aggressiveness": "moderate",
        "subtitle_style": subtitle_style,
        "subtitle_style_reason": "Most common style across analyzed clips",
        "music_search_query": f"{mood} background music",
        "music_mood": "motivational",
        "music_bpm_preference": "medium",
        "edit_notes": "Sequential edit with balanced pacing.",
        "hook_strategy": "Open with the most engaging clip.",
        "reel_title_suggestion": "Watch this to the end"
    }

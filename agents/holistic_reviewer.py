"""
agents/holistic_reviewer.py

HolisticReviewer — Human-like view of all clips.
Receives ALL transcripts + analyses, produces structured HolisticReview
for the EditDirector to use.
"""

import json
import logging
from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)
LLM_MODEL = "llama-3.3-70b-versatile"

REVIEW_PROMPT = """You are an experienced video editor scanning raw clips like a human.

You have {n_clips} clip(s). For each you know: transcript (what's said), visual analysis (quality, energy, hook strength).

Your job: produce a holistic review — like watching all rushes and forming one impression.

Respond ONLY with valid JSON. No markdown.

{{
  "overall_impression": "2-3 sentences: what's the content about, how does it feel, strengths/weaknesses",
  "best_clip_for_hook": 0,
  "best_clip_for_cta": 0,
  "clips_to_cut": [1, 2],
  "pacing_suggestion": "fast start, slow middle, punchy end | normal | dynamic",
  "creative_notes": "2-3 sentences: unconventional ideas, what could surprise the viewer"
}}

CLIP DATA:
{clip_summaries}
"""


def _build_clip_summaries(transcripts: list[dict], analyses: list[dict]) -> str:
    """Build compact per-clip summary for the prompt."""
    lines = []
    for i, t in enumerate(transcripts):
        a = next((x for x in analyses if x.get("clip_index") == i), {})
        lines.append(
            f"Clip {i}: \"{t.get('full_text', '')[:150]}...\" | "
            f"visual={a.get('visual_quality')} hook={a.get('visual_hook_strength')}/10 "
            f"energy={a.get('speaker_energy')}"
        )
    return "\n".join(lines)


def create_holistic_review(
    transcripts: list[dict],
    analyses: list[dict],
) -> dict:
    """
    Produce human-like holistic review of all clips for EditDirector.
    """
    if not has_keys():
        raise RuntimeError("[HolisticReviewer] No Groq API keys — requires LLM to produce holistic review")

    n = len(transcripts)
    if n == 0:
        return {
            "overall_impression": "",
            "best_clip_for_hook": 0,
            "best_clip_for_cta": 0,
            "clips_to_cut": [],
            "pacing_suggestion": "normal",
            "creative_notes": "",
        }

    summaries = _build_clip_summaries(transcripts, analyses)
    prompt = REVIEW_PROMPT.format(n_clips=n, clip_summaries=summaries)

    try:
        logger.info(f"[HolisticReviewer] Analyzing {n} clips holistically...")
        client = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a video editor. Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.5,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        review = json.loads(raw)

        # Clamp indices to valid range only (safety, not creative override)
        review["best_clip_for_hook"] = max(0, min(int(review.get("best_clip_for_hook", 0)), n - 1))
        review["best_clip_for_cta"] = max(0, min(int(review.get("best_clip_for_cta", n - 1)), n - 1))
        review["clips_to_cut"] = [c for c in review.get("clips_to_cut", []) if 0 <= c < n]

        logger.info(f"[HolisticReviewer] impression={review.get('overall_impression', '')[:60]}...")
        return review

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[HolisticReviewer] Failed: {e}")
        raise

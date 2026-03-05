"""
agents/subtitle_verifier.py

Agent 6 — SubtitleVerifier
Runs at the burn-subtitles step. Verifies transcription quality,
judges whether the video needs subtitles, and suggests a style.
All decisions from the LLM — no hardcoded logic.
"""

import json
import logging
from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)
LLM_MODEL = "llama-3.3-70b-versatile"

# Available styles — agent chooses one
SUBTITLE_STYLES = "hormozi, minimal, neon, fire, karaoke, purple"

VERIFY_PROMPT = """You are a subtitle specialist for Instagram Reels.

You have the final transcript (word-level timestamps) and video context.
Your job: verify the transcription and decide whether to burn subtitles.

TRANSCRIPT (words that will appear in the reel):
{transcript_summary}

FULL TRANSCRIPT TEXT:
"{full_text}"

VIDEO CONTEXT:
- Mood: {overall_mood}
- Energy: {overall_energy}
- Creative direction: {creative_direction}
- Caption hook: "{caption_hook}"
- Word count: {word_count}
- Estimated reel duration: {duration_sec}s

TASKS:
1. VERIFY: Is the transcription coherent? Any obvious errors or gibberish?
2. JUDGE: Does this video NEED subtitles?
   - Consider: speech-heavy content benefits from subs; music-only or b-roll may not
   - Sparse speech (< 5 words) or no clear dialogue → often skip
   - Talking head, educational, motivational → usually add
3. If subtitles needed: pick ONE style from [{subtitle_styles}]
   - hormozi: bold white/yellow, high contrast (business, motivational)
   - minimal: clean white, subtle (lifestyle, calm)
   - neon: cyan/magenta glow (tech, futuristic)
   - fire: white/orange (energy, hype)
   - karaoke: white/green highlight (music, singalong feel)
   - purple: white/purple (creative, artistic)

Respond ONLY with valid JSON. No markdown.

{{
  "transcription_verified": true,
  "transcription_notes": "one sentence on quality",
  "needs_subtitles": true,
  "needs_subtitles_reason": "one sentence",
  "subtitle_style": "hormozi",
  "subtitle_style_reason": "one sentence"
}}"""


def verify_and_decide(
    all_words: list[dict],
    edit_plan: dict,
    transcripts: list[dict],
) -> dict:
    """
    Verify transcription, judge if subtitles needed, suggest style.
    Returns: {needs_subtitles: bool, subtitle_style: str, ...}
    """
    if not has_keys():
        raise RuntimeError("[SubtitleVerifier] No Groq API keys — requires LLM to verify subtitles")

    full_text = " ".join(w["word"] for w in all_words) if all_words else ""
    word_count = len(all_words)
    duration = sum(t.get("duration_sec", 0) for t in transcripts) or 1.0

    # Build transcript summary (first/last words, sample)
    if all_words:
        sample = " ".join(w["word"] for w in all_words[:20])
        if len(all_words) > 20:
            sample += " ..."
        transcript_summary = sample
    else:
        transcript_summary = "(no words)"

    caption = edit_plan.get("caption", {})
    prompt = VERIFY_PROMPT.format(
        transcript_summary=transcript_summary,
        full_text=full_text[:500],
        overall_mood=edit_plan.get("overall_mood", ""),
        overall_energy=edit_plan.get("overall_energy", ""),
        creative_direction=edit_plan.get("creative_direction", ""),
        caption_hook=caption.get("hook", ""),
        word_count=word_count,
        duration_sec=round(duration, 1),
        subtitle_styles=SUBTITLE_STYLES,
    )

    try:
        logger.info("[SubtitleVerifier] Verifying transcription and deciding subtitle need...")
        client = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        needs = result.get("needs_subtitles", bool(all_words))
        style = result.get("subtitle_style", "hormozi")

        # Validate style is one of the 6
        valid = {"hormozi", "minimal", "neon", "fire", "karaoke", "purple"}
        if style.lower() not in valid:
            style = "hormozi"

        logger.info(
            f"[SubtitleVerifier] needs_subtitles={needs} | style={style} | "
            f"reason={result.get('needs_subtitles_reason', '')[:50]}"
        )
        return {
            "needs_subtitles": needs,
            "subtitle_style": style,
            "subtitle_style_reason": result.get("subtitle_style_reason", ""),
            "transcription_verified": result.get("transcription_verified", True),
            "transcription_notes": result.get("transcription_notes", ""),
        }
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[SubtitleVerifier] Failed: {e}")
        raise

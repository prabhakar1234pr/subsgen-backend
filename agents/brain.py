"""
agents/brain.py

Agent 3 — The Brain (Director + Narrative Planner)
Uses Llama 3.3 70B via Groq.

This is the core intelligence of the system. It:
  - Reads ALL transcripts (what is being said)
  - Reads ALL VLM analyses (what is being shown)
  - Scores each clip (keep vs cut)
  - Decides narrative order (hook -> value -> CTA)
  - Decides EXACT trim points per clip (start_sec, end_sec)
  - Picks subtitle style based on content personality
  - Writes caption + hashtags
  - Instructs music supervisor on mood
"""

import json
import logging
from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)
LLM_MODEL = "llama-3.3-70b-versatile"

BRAIN_PROMPT = """You are an elite Instagram Reels director and content strategist.

You have {n_clips} raw video clip(s) to turn into ONE viral Instagram Reel.
Below is everything you know about each clip — its transcript AND visual analysis.

═══════════════════════════════════════
CLIP DATA:
{clip_data_json}
═══════════════════════════════════════

Your job is to produce a complete, precise EditPlan.

SCORING RULES:
- Score each clip 1-10 for "keep_score". Score below 4 = cut the clip entirely.
- A clip with no speech (has_speech=false) can still be kept if visual_score >= 7.
- Prefer clips with strong hooks, clear speech, good lighting.

NARRATIVE RULES:
- Hook first: the most attention-grabbing moment goes at the start (first 3 seconds matter most)
- Value middle: the core content/teaching/story
- CTA end: call to action, punchline, or strong close
- If a clip has filler at the start ("um", "so", "okay so today"), trim it — give exact start_sec

TRIM RULES:
- For each kept clip, specify exact start_sec and end_sec to use
- start_sec: skip filler openers, start at the first impactful word
- end_sec: cut before trailing silence or weak endings
- Use the word timestamps in the transcript to be precise
- Min clip length after trimming: 2 seconds

CAPTION RULES:
- Hook line: punchy, <10 words, no emoji in first line
- Body: 2-3 lines of value
- CTA: one clear action
- Hashtags: 5 relevant niche hashtags (not generic like #reels)

Respond ONLY with a valid JSON object. No explanation, no markdown fences.

{{
  "clips": [
    {{
      "clip_index": 0,
      "keep": true,
      "keep_score": 8,
      "keep_reason": "strong hook, clear speech",
      "narrative_role": "hook | value | cta | broll",
      "narrative_order": 0,
      "trim_start_sec": 1.4,
      "trim_end_sec": 18.2,
      "trim_reason": "skip filler intro 'okay so', end before trailing silence"
    }}
  ],
  "subtitle_style": "hormozi | minimal | neon | fire | karaoke | purple",
  "subtitle_style_reason": "one sentence",
  "overall_mood": "motivational | educational | entertaining | emotional | inspirational",
  "overall_energy": "low | medium | high",
  "music_search_query": "specific 2-4 word Pixabay search query",
  "music_mood": "motivational | chill | energy | uplifting | cinematic",
  "music_bpm_preference": "slow | medium | fast",
  "caption": {{
    "hook": "hook line here",
    "body": "line1\\nline2\\nline3",
    "cta": "call to action here",
    "hashtags": ["#niche1", "#niche2", "#niche3", "#niche4", "#niche5"]
  }},
  "director_notes": "2-3 sentences on the edit strategy",
  "estimated_reel_duration_sec": 30
}}"""


def _build_clip_data(transcripts: list[dict], analyses: list[dict]) -> list[dict]:
    """Merge transcript + visual analysis per clip for the Brain prompt."""
    merged = []
    for t in transcripts:
        idx = t["clip_index"]
        a = next((x for x in analyses if x["clip_index"] == idx), {})
        merged.append({
            "clip_index":       idx,
            "clip_name":        t["clip_name"],
            "duration_sec":     t["duration_sec"],
            # Transcript data
            "has_speech":       t["has_speech"],
            "speech_ratio":     t["speech_ratio"],
            "full_transcript":  t["full_text"],
            "first_words":      " ".join(w["word"] for w in t["words"][:15]) if t["words"] else "",
            "last_words":       " ".join(w["word"] for w in t["words"][-10:]) if t["words"] else "",
            "word_count":       len(t["words"]),
            "first_speech_at":  t["words"][0]["start"] if t["words"] else 0,
            "last_speech_at":   t["words"][-1]["end"] if t["words"] else t["duration_sec"],
            # Visual data
            "visual_quality":   a.get("visual_quality", "unknown"),
            "visual_score":     a.get("overall_visual_score", 5),
            "hook_strength":    a.get("visual_hook_strength", 5),
            "speaker_energy":   a.get("speaker_energy", "medium"),
            "lighting":         a.get("lighting_quality", "decent"),
            "setting":          a.get("setting", "indoor"),
            "content_type":     a.get("content_type", "talking_head"),
            "suggested_style":  a.get("recommended_subtitle_style", "hormozi"),
        })
    return merged


def create_edit_plan(transcripts: list[dict], analyses: list[dict]) -> dict:
    """
    The Brain: synthesize transcripts + visual analyses into a complete EditPlan.
    """
    if not has_keys():
        logger.warning("[Brain] No Groq keys — using fallback edit plan")
        return _fallback_plan(transcripts, analyses)

    clip_data = _build_clip_data(transcripts, analyses)
    prompt = BRAIN_PROMPT.format(
        n_clips=len(clip_data),
        clip_data_json=json.dumps(clip_data, indent=2)
    )

    try:
        logger.info(f"[Brain] Analyzing {len(clip_data)} clips (transcripts + vision)...")
        client = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an elite Instagram Reels director. "
                        "You think deeply about narrative, viewer psychology, and viral content. "
                        "Always respond with valid JSON only."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.4,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        plan = json.loads(raw)

        # Validate + fix clips list
        n = len(transcripts)
        if "clips" not in plan or not plan["clips"]:
            plan["clips"] = _default_clips(transcripts)

        # Ensure all clips are present, clamp times
        for clip_plan in plan["clips"]:
            idx = clip_plan.get("clip_index", 0)
            t = next((x for x in transcripts if x["clip_index"] == idx), None)
            if t:
                dur = t["duration_sec"]
                clip_plan["trim_start_sec"] = max(0.0, float(clip_plan.get("trim_start_sec", 0)))
                clip_plan["trim_end_sec"]   = min(dur, float(clip_plan.get("trim_end_sec", dur)))
                # Ensure at least 2 seconds
                if clip_plan["trim_end_sec"] - clip_plan["trim_start_sec"] < 2.0:
                    clip_plan["trim_start_sec"] = 0.0
                    clip_plan["trim_end_sec"]   = dur

        kept = [c for c in plan["clips"] if c.get("keep", True)]
        logger.info(
            f"[Brain] Plan: {len(kept)}/{n} clips kept, "
            f"style={plan.get('subtitle_style')}, "
            f"mood={plan.get('overall_mood')}, "
            f"music='{plan.get('music_search_query')}'"
        )
        return plan

    except json.JSONDecodeError as e:
        logger.error(f"[Brain] Invalid JSON response: {e}")
        return _fallback_plan(transcripts, analyses)
    except Exception as e:
        logger.error(f"[Brain] Error: {e}")
        return _fallback_plan(transcripts, analyses)


def _default_clips(transcripts: list[dict]) -> list[dict]:
    clips = []
    for i, t in enumerate(transcripts):
        clips.append({
            "clip_index":      t["clip_index"],
            "keep":            True,
            "keep_score":      6,
            "keep_reason":     "default — no AI scoring available",
            "narrative_role":  "value",
            "narrative_order": i,
            "trim_start_sec":  t["words"][0]["start"] if t["words"] else 0.0,
            "trim_end_sec":    t["duration_sec"],
            "trim_reason":     "no LLM trimming available",
        })
    return clips


def _fallback_plan(transcripts: list[dict], analyses: list[dict]) -> dict:
    styles = [a.get("recommended_subtitle_style", "hormozi") for a in analyses]
    style  = max(set(styles), key=styles.count) if styles else "hormozi"
    return {
        "clips":                  _default_clips(transcripts),
        "subtitle_style":         style,
        "subtitle_style_reason":  "Most common style across clips",
        "overall_mood":           "motivational",
        "overall_energy":         "medium",
        "music_search_query":     "motivational background",
        "music_mood":             "motivational",
        "music_bpm_preference":   "medium",
        "caption": {
            "hook":      "You need to see this.",
            "body":      "Watch till the end.\nThis changes everything.",
            "cta":       "Follow for more.",
            "hashtags":  ["#reels", "#viral", "#content", "#creator", "#trending"]
        },
        "director_notes":              "Sequential edit, no AI director available.",
        "estimated_reel_duration_sec": 30,
    }

"""
agents/brain.py

Agent 3 — EditDirector (Brain)
Uses Llama 3.3 70B via Groq.

Creative, generative edit planning:
  - Reads holistic review + transcripts + VLM analyses
  - Scores clips, decides order, trim points
  - Picks transitions per segment (fade, wipe, slide)
  - Creative direction, music params, caption
"""

import json
import logging
from groq import Groq
from agents.key_manager import next_key, has_keys
from agents.schemas import ensure_clip_edit_fields, ensure_edit_plan_fields

logger = logging.getLogger(__name__)
LLM_MODEL = "llama-3.3-70b-versatile"

BRAIN_PROMPT = """You are an elite Instagram Reels director. Be CREATIVE. Surprise the viewer.
Don't always put the obvious hook first. Consider unconventional order. Pick transitions that match the energy of each cut.

You have {n_clips} raw video clip(s) to turn into ONE viral Instagram Reel.
{holistic_context}

═══════════════════════════════════════
CLIP DATA:
{clip_data_json}
═══════════════════════════════════════

Your job: produce a complete, creative EditPlan.

SCORING: keep_score 1-10. Below 4 = cut. Prefer strong hooks, clear speech, good lighting.

NARRATIVE: Hook first, value middle, CTA end. Trim filler ("um", "so") — give exact start_sec/end_sec.

TRANSITIONS (per kept clip): Pick what fits the energy.
- transition_in: "fade" | "wipe_left" | "wipe_right" | "slide_left" | "slide_right" | "none"
- transition_out: same options (used when cutting TO the next clip)
- transition_duration_sec: 0.2 to 0.8
- pacing_note: "quick_cut" | "hold" | "normal"

CREATIVE: creative_direction = "bold cuts" | "smooth flow" | "punchy" | "cinematic"

MUSIC: music_volume 0.05-0.2, duck_strength "light"|"medium"|"heavy", music_creative_brief for unusual/contrasting choices.

Respond ONLY with valid JSON. No markdown.

{{
  "clips": [
    {{
      "clip_index": 0,
      "keep": true,
      "keep_score": 8,
      "keep_reason": "strong hook",
      "narrative_role": "hook | value | cta | broll",
      "narrative_order": 0,
      "trim_start_sec": 1.4,
      "trim_end_sec": 18.2,
      "trim_reason": "skip filler",
      "transition_in": "fade",
      "transition_out": "fade",
      "transition_duration_sec": 0.35,
      "pacing_note": "normal"
    }}
  ],
  "subtitle_style": "hormozi | minimal | neon | fire | karaoke | purple",
  "subtitle_style_reason": "one sentence",
  "overall_mood": "motivational | educational | entertaining | emotional | inspirational",
  "overall_energy": "low | medium | high",
  "music_search_query": "2-4 word search query",
  "music_mood": "motivational | chill | energy | uplifting | cinematic",
  "music_bpm_preference": "slow | medium | fast",
  "creative_direction": "bold cuts | smooth flow | punchy | cinematic",
  "music_volume": 0.12,
  "duck_strength": "light | medium | heavy",
  "music_fade_in_sec": 1.0,
  "music_fade_out_sec": 2.0,
  "music_creative_brief": "optional: unusual or contrasting music idea",
  "caption": {{"hook": "...", "body": "...", "cta": "...", "hashtags": ["#a","#b","#c","#d","#e"]}},
  "director_notes": "2-3 sentences",
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


def create_edit_plan(
    transcripts: list[dict],
    analyses: list[dict],
    holistic_review: dict | None = None,
) -> dict:
    """
    EditDirector: synthesize holistic review + transcripts + analyses into creative EditPlan.
    """
    if not has_keys():
        logger.warning("[Brain] No Groq keys — using fallback edit plan")
        return _fallback_plan(transcripts, analyses)

    clip_data = _build_clip_data(transcripts, analyses)
    holistic_context = ""
    if holistic_review and holistic_review.get("overall_impression"):
        holistic_context = f"HOLISTIC REVIEW: {holistic_review.get('overall_impression', '')}\nPacing: {holistic_review.get('pacing_suggestion', '')}\nCreative notes: {holistic_review.get('creative_notes', '')}\n\n"
    else:
        holistic_context = ""

    prompt = BRAIN_PROMPT.format(
        n_clips=len(clip_data),
        holistic_context=holistic_context,
        clip_data_json=json.dumps(clip_data, indent=2),
    )

    try:
        logger.info(f"[Brain] Analyzing {len(clip_data)} clips | creative edit plan (transitions, music)...")
        client = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an elite Instagram Reels director. Be creative. "
                        "Pick transitions that match energy. Surprise the viewer. "
                        "Always respond with valid JSON only."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.6,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        plan = json.loads(raw)

        # Validate + fix clips list
        n = len(transcripts)
        if "clips" not in plan or not plan["clips"]:
            plan["clips"] = _default_clips(transcripts)

        # Ensure all clips are present, clamp times, add transition fields
        for clip_plan in plan["clips"]:
            ensure_clip_edit_fields(clip_plan)
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

        ensure_edit_plan_fields(plan)
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
        c = {
            "clip_index":      t.get("clip_index", i),
            "keep":            True,
            "keep_score":      6,
            "keep_reason":     "default — no AI scoring available",
            "narrative_role":  "value",
            "narrative_order": i,
            "trim_start_sec":  t["words"][0]["start"] if t.get("words") else 0.0,
            "trim_end_sec":    t["duration_sec"],
            "trim_reason":     "no LLM trimming available",
        }
        ensure_clip_edit_fields(c)
        clips.append(c)
    return clips


def _fallback_plan(transcripts: list[dict], analyses: list[dict]) -> dict:
    styles = [a.get("recommended_subtitle_style", "hormozi") for a in analyses]
    style  = max(set(styles), key=styles.count) if styles else "hormozi"
    plan = {
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
    return ensure_edit_plan_fields(plan)

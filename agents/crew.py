"""
agents/crew.py

Orchestrates all 4 agents in sequence.
Single entry point used by the FastAPI router.

Pipeline:
  1. Transcriber    — Groq Whisper Large v3  (what is being said)
  2. VideoAnalyst   — Groq Llama 4 Scout VLM (what is being shown)
  3. Brain          — Groq Llama 3.3 70B     (narrative + edit plan + caption)
  4. MusicSupervisor— Groq Llama 3.3 70B + Pixabay (find + download music)

Returns a ReelBlueprint consumed by the FFmpeg producer.
"""

import logging
import tempfile
from pathlib import Path

from agents.transcriber      import transcribe_clip
from agents.video_analyst    import analyze_clip
from agents.brain            import create_edit_plan
from agents.music_supervisor import find_and_download_music

logger = logging.getLogger(__name__)


def run_ai_pipeline(clip_paths: list[Path]) -> dict:
    """
    Run the full 4-agent AI pipeline on raw video clips.

    Returns ReelBlueprint:
    {
        "ordered_clips":       [(Path, float, float), ...],  # (path, trim_start, trim_end)
        "edit_plan":           dict,      # full Brain JSON
        "transcripts":         list[dict],
        "analyses":            list[dict],
        "music_path":          Path | None,
        "subtitle_style":      str,
        "caption":             dict,      # {hook, body, cta, hashtags}
        "all_words":           list[dict] # merged word timestamps for subtitle burn
    }
    """
    n = len(clip_paths)
    logger.info(f"╔══ AI Pipeline starting: {n} clip(s) ══╗")

    # ── Agent 1: Transcribe every clip first ──────────────────────────
    logger.info(f"[1/4] Transcriber — Groq Whisper Large v3")
    transcripts = []
    for i, clip in enumerate(clip_paths):
        logger.info(f"  Transcribing clip {i+1}/{n}: {clip.name}")
        t = transcribe_clip(clip, clip_index=i)
        transcripts.append(t)
        logger.info(f"  → '{t['full_text'][:80]}...' ({len(t.get('words', []))} words)")

    # ── Agent 2: Visual analysis (with transcript context) ────────────
    logger.info(f"[2/4] VideoAnalyst — Llama 4 Scout VLM")
    analyses = []
    for i, clip in enumerate(clip_paths):
        logger.info(f"  Analyzing clip {i+1}/{n} visually...")
        a = analyze_clip(clip, transcript=transcripts[i], clip_index=i)
        analyses.append(a)
        logger.info(f"  → quality={a.get('visual_quality')}, hook={a.get('visual_hook_strength')}/10")

    # ── Agent 3: Brain — narrative + edit plan + caption ─────────────
    logger.info(f"[3/4] Brain — Llama 3.3 70B (narrative + edit plan + caption)")
    edit_plan = create_edit_plan(transcripts, analyses)

    kept_clips = [c for c in edit_plan.get("clips", []) if c.get("keep", True)]
    logger.info(f"  → Keeping {len(kept_clips)}/{n} clips")
    logger.info(f"  → Style: {edit_plan.get('subtitle_style')}")
    logger.info(f"  → Caption hook: \"{edit_plan.get('caption', {}).get('hook', '')}\"")

    # Sort kept clips by narrative_order
    kept_clips.sort(key=lambda c: c.get("narrative_order", c["clip_index"]))

    # Build ordered clip list with exact trim points
    ordered_clips = []
    for clip_plan in kept_clips:
        idx         = clip_plan["clip_index"]
        clip_path   = clip_paths[idx]
        trim_start  = float(clip_plan.get("trim_start_sec", 0.0))
        trim_end    = float(clip_plan.get("trim_end_sec", transcripts[idx]["duration_sec"]))
        ordered_clips.append((clip_path, trim_start, trim_end))

    # ── Agent 4: Music Supervisor ─────────────────────────────────────
    logger.info(f"[4/4] MusicSupervisor — Llama 3.3 70B + Pixabay")
    tmp_dir    = Path(tempfile.gettempdir())
    music_path = find_and_download_music(edit_plan, tmp_dir)
    logger.info(f"  → Music: {'downloaded ✓' if music_path else 'not available'}")

    # Build merged word list for the kept clips (for subtitle burn)
    # Re-offset word timestamps to account for ordering + trimming
    all_words  = []
    time_cursor = 0.0
    for clip_path, trim_start, trim_end in ordered_clips:
        idx = next(i for i, p in enumerate(clip_paths) if p == clip_path)
        t   = transcripts[idx]
        for w in t.get("words", []):
            if trim_start <= w["start"] <= trim_end:
                offset_start = time_cursor + (w["start"] - trim_start)
                offset_end   = time_cursor + (w["end"]   - trim_start)
                all_words.append({
                    "word":  w["word"],
                    "start": round(offset_start, 3),
                    "end":   round(offset_end,   3),
                })
        clip_duration = trim_end - trim_start
        time_cursor  += clip_duration

    logger.info(f"╚══ AI Pipeline complete — {len(all_words)} subtitle words, {len(ordered_clips)} clips ══╝")

    return {
        "ordered_clips":  ordered_clips,
        "edit_plan":      edit_plan,
        "transcripts":    transcripts,
        "analyses":       analyses,
        "music_path":     music_path,
        "subtitle_style": edit_plan.get("subtitle_style", "hormozi"),
        "caption":        edit_plan.get("caption", {}),
        "all_words":      all_words,
    }

"""
agents/flows/reel_flow.py

AI reel pipeline: transcribe → analyze → holistic review → edit plan → music → blueprint.
Returns ReelBlueprint compatible with the reel_pipeline router.
"""

import logging
import tempfile
from pathlib import Path

from agents.transcriber import transcribe_clip
from agents.video_analyst import analyze_clip
from agents.brain import create_edit_plan
from agents.music_supervisor import find_and_download_music
from agents.holistic_reviewer import create_holistic_review
from agents.subtitle_verifier import verify_and_decide

logger = logging.getLogger(__name__)


def run_reel_flow(clip_paths: list[Path]) -> dict:
    """
    Run the AI reel pipeline and return the ReelBlueprint.
    """
    n = len(clip_paths)
    logger.info(f"╔══ Reel pipeline starting: {n} clip(s) ══╗")

    # 1. Transcribe
    logger.info("[1/6] Transcriber — Groq Whisper Large v3")
    transcripts = []
    for i, clip in enumerate(clip_paths):
        logger.info(f"  Transcribing clip {i+1}/{n}: {clip.name}")
        t = transcribe_clip(clip, clip_index=i)
        transcripts.append(t)
        logger.info(f"  → '{t['full_text'][:80]}...' ({len(t.get('words', []))} words)")

    # 2. Visual analysis
    logger.info("[2/6] VideoAnalyst — Llama 4 Scout VLM")
    analyses = []
    for i, clip in enumerate(clip_paths):
        logger.info(f"  Analyzing clip {i+1}/{n} visually...")
        a = analyze_clip(clip, transcript=transcripts[i], clip_index=i)
        analyses.append(a)
        logger.info(f"  → quality={a.get('visual_quality')}, hook={a.get('visual_hook_strength')}/10")

    # 3. Holistic review
    logger.info("[3/6] HolisticReviewer")
    holistic_review = create_holistic_review(transcripts, analyses)

    # 4. Edit plan (Brain)
    logger.info("[4/6] EditDirector — Llama 3.3 70B")
    edit_plan = create_edit_plan(
        transcripts,
        analyses,
        holistic_review=holistic_review,
    )
    kept = [c for c in edit_plan.get("clips", []) if c.get("keep", True)]
    logger.info(f"  → Keeping {len(kept)}/{n} clips")

    # 5. Music
    logger.info("[5/6] MusicSupervisor — Internet Archive")
    tmp_dir = Path(tempfile.gettempdir())
    music_path = find_and_download_music(edit_plan, tmp_dir)
    logger.info(f"  → Music: {'downloaded ✓' if music_path else 'not available'}")

    # 6. Build blueprint
    kept_clips = [c for c in edit_plan.get("clips", []) if c.get("keep", True)]
    kept_clips.sort(key=lambda c: c.get("narrative_order", c["clip_index"]))

    ordered_clips = []
    for clip_plan in kept_clips:
        idx = clip_plan["clip_index"]
        clip_path = clip_paths[idx]
        trim_start = clip_plan.get("trim_start_sec")
        trim_end = clip_plan.get("trim_end_sec")
        trans_out = clip_plan.get("transition_out")
        trans_dur = clip_plan.get("transition_duration_sec")
        if trim_start is None or trim_end is None:
            raise ValueError(f"[ReelFlow] Clip {idx} missing trim_start_sec or trim_end_sec from EditDirector")
        if trans_out is None or trans_dur is None:
            raise ValueError(f"[ReelFlow] Clip {idx} missing transition_out or transition_duration_sec from EditDirector")
        ordered_clips.append((clip_path, float(trim_start), float(trim_end), trans_out, float(trans_dur)))

    all_words = []
    time_cursor = 0.0
    for item in ordered_clips:
        clip_path, trim_start, trim_end = item[0], item[1], item[2]
        idx = next((i for i, p in enumerate(clip_paths) if p == clip_path), 0)
        t = transcripts[idx]
        for w in t.get("words", []):
            if trim_start <= w["start"] <= trim_end:
                offset_start = time_cursor + (w["start"] - trim_start)
                offset_end = time_cursor + (min(w["end"], trim_end) - trim_start)
                all_words.append({
                    "word": w["word"],
                    "start": round(offset_start, 3),
                    "end": round(offset_end, 3),
                })
        clip_duration = trim_end - trim_start
        time_cursor += clip_duration

    logger.info("[6/6] SubtitleVerifier — verify transcription, decide if subs needed")
    verifier_result = verify_and_decide(all_words, edit_plan, transcripts)
    needs_subtitles = verifier_result["needs_subtitles"]
    subtitle_style = verifier_result["subtitle_style"]
    logger.info(f"╚══ Reel pipeline complete — {len(all_words)} words, {len(ordered_clips)} clips | subs={needs_subtitles} style={subtitle_style} ══╝")

    return {
        "ordered_clips": ordered_clips,
        "edit_plan": edit_plan,
        "transcripts": transcripts,
        "analyses": analyses,
        "music_path": music_path,
        "needs_subtitles": needs_subtitles,
        "subtitle_style": subtitle_style,
        "subtitle_verifier": verifier_result,
        "caption": edit_plan.get("caption", {}),
        "all_words": all_words,
    }

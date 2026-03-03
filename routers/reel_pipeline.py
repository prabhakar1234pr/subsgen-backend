"""
routers/reel_pipeline.py

POST /api/reel-pipeline
POST /api/reel-pipeline/caption  (returns last caption, no video)

Full AI pipeline:
  Agent 1 — Groq Whisper Large v3       (transcribe each clip)
  Agent 2 — Groq Llama 4 Scout VLM      (visual analysis per clip)
  Agent 3 — Groq Llama 3.3 70B Brain    (narrative + edit plan + caption)
  Agent 4 — Groq Llama 3.3 70B + Internet Archive (find + download music)
  FFmpeg  — precise trim, 9:16, concat, mix music, burn subs
  → returns reel.mp4 + X-Caption header
"""

import json
import logging
import os
import time

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from agents.crew             import run_ai_pipeline
from agents.key_manager      import has_keys, key_count
from services.subtitle       import generate_ass_subtitles, burn_subtitles
from services.video_editor   import produce_reel
from services.music_selector import mix_music
from utils.file_handler      import TempFileHandler

logger     = logging.getLogger(__name__)
router     = APIRouter()
MAX_MB     = 500
_last_caption = {}   # simple in-memory store for last caption


def _mix_music(video_path, music_path, out, vol=0.10, fade_in=1.0, fade_out=2.0):
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True)
    dur = float(r.stdout.strip())
    fs  = max(0.0, dur - fade_out)
    fc  = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=duration={dur},"
        f"volume={vol},afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fs:.3f}:d={fade_out}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    subprocess.run([
        "ffmpeg", "-i", str(video_path), "-i", str(music_path),
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", "-y", str(out),
    ], check=True, capture_output=True)


@router.get("/reel-pipeline/status")
async def pipeline_status():
    return {
        "groq_keys_loaded": key_count(),
        "groq_ready":       has_keys(),
        "models": {
            "stt":    "whisper-large-v3 (Groq)",
            "vision": "meta-llama/llama-4-scout-17b-16e-instruct (Groq)",
            "brain":  "llama-3.3-70b-versatile (Groq)",
            "music":  "llama-3.3-70b-versatile (Groq) + Internet Archive",
            "edit":   "FFmpeg",
        }
    }


@router.get("/reel-pipeline/last-caption")
async def get_last_caption():
    if not _last_caption:
        return JSONResponse({"error": "No caption generated yet"}, status_code=404)
    return JSONResponse(_last_caption)


@router.post("/reel-pipeline")
async def process_reel_pipeline(
    background_tasks: BackgroundTasks,
    videos: list[UploadFile] = File(...),
):
    """
    Upload raw clips → AI pipeline → one finished reel.mp4
    Caption is returned in X-Caption response header (JSON encoded).
    Also available via GET /api/reel-pipeline/last-caption
    """
    global _last_caption
    if not videos:
        raise HTTPException(status_code=400, detail="No videos uploaded")

    handler = TempFileHandler()
    wall    = time.time()

    try:
        # ── 1. Save uploads ────────────────────────────────────────────
        logger.info(f"[PIPELINE] Saving {len(videos)} uploads...")
        clip_paths, total_bytes = [], 0
        for v in videos:
            content      = await v.read()
            total_bytes += len(content)
            if total_bytes > MAX_MB * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Total upload must be under {MAX_MB}MB")
            ext = os.path.splitext(v.filename or ".mp4")[1] or ".mp4"
            clip_paths.append(handler.save_upload(content, ext))
        logger.info(f"[PIPELINE] Saved {total_bytes/1024/1024:.1f}MB")

        # ── 2. Run 4-agent AI pipeline ─────────────────────────────────
        logger.info("[PIPELINE] Starting 4-agent AI pipeline...")
        t_ai     = time.time()
        blueprint = run_ai_pipeline(clip_paths)
        logger.info(f"[PIPELINE] AI pipeline done in {time.time()-t_ai:.1f}s")

        ordered_clips  = blueprint["ordered_clips"]
        subtitle_style = blueprint["subtitle_style"]
        music_path     = blueprint["music_path"]
        all_words      = blueprint["all_words"]
        caption        = blueprint["caption"]
        edit_plan      = blueprint["edit_plan"]

        _last_caption = caption   # store for later retrieval

        if not ordered_clips:
            raise HTTPException(400, "Brain decided all clips should be cut — please upload better content")

        # ── 3. FFmpeg: trim + reframe + concat ─────────────────────────
        t_edit   = time.time()
        logger.info(f"[PIPELINE] Producing reel: {len(ordered_clips)} clips...")
        stitched = handler.create_temp_path(".mp4")
        produce_reel(ordered_clips, stitched)
        for p, _, _ in ordered_clips:
            handler.cleanup_file(p)
        logger.info(f"[PIPELINE] Reel produced in {time.time()-t_edit:.1f}s")

        # ── 4. Mix music ───────────────────────────────────────────────
        with_music = handler.create_temp_path(".mp4")
        if music_path and music_path.exists():
            logger.info("[PIPELINE] Mixing downloaded music...")
            _mix_music(stitched, music_path, with_music)
            music_path.unlink(missing_ok=True)
        else:
            logger.info(f"[PIPELINE] No downloaded music — using bundled fallback (mood={edit_plan.get('music_mood','motivational')})")
            mix_music(stitched, with_music, mood=edit_plan.get("music_mood", "motivational"))
        handler.cleanup_file(stitched)

        # ── 5. Burn subtitles (using Brain's pre-computed word list) ───
        t_subs = time.time()
        if not all_words:
            logger.warning("[PIPELINE] No words from Brain — subtitles skipped")
            final = with_music
        else:
            logger.info(f"[PIPELINE] Burning {len(all_words)} subtitle words (style={subtitle_style})...")
            subs  = handler.create_temp_path(".ass")
            generate_ass_subtitles(all_words, subs, style=subtitle_style)
            final = handler.create_temp_path(".mp4")
            burn_subtitles(with_music, subs, final)
            handler.cleanup_file(with_music)
            handler.cleanup_file(subs)
        logger.info(f"[PIPELINE] Subtitles done in {time.time()-t_subs:.1f}s")

        size_mb = os.path.getsize(final) / 1024 / 1024
        logger.info(f"[PIPELINE COMPLETE] {size_mb:.1f}MB in {time.time()-wall:.1f}s total")
        logger.info(f"[PIPELINE] Caption: \"{caption.get('hook','')}\"")

        # Encode caption into response header so frontend can display it
        caption_header = json.dumps(caption, ensure_ascii=False)

        # Cleanup final file after response is sent
        background_tasks.add_task(handler.cleanup_file, final)

        return FileResponse(
            path        = str(final),
            media_type  = "video/mp4",
            filename    = "reel.mp4",
            headers     = {
                "X-Caption": caption_header,
                "X-Subtitle-Style": subtitle_style,
                "X-Music-Mood": edit_plan.get("music_mood", ""),
            }
        )

    except HTTPException:
        handler.cleanup()
        raise
    except Exception as e:
        logger.error(f"[PIPELINE ERROR] {e}", exc_info=True)
        handler.cleanup()
        raise HTTPException(500, f"Pipeline failed: {str(e)}")

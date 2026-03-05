"""
routers/reel_pipeline.py

POST /api/reel-pipeline
POST /api/reel-pipeline/caption  (returns last caption, no video)

Full AI pipeline:
  Agent 1 — Groq Whisper Large v3       (transcribe each clip)
  Agent 2 — Groq Llama 4 Scout VLM      (visual analysis per clip)
  Agent 3 — HolisticReviewer + EditDirector (CrewAI Flow)
  Agent 4 — Groq Llama 3.3 70B + Internet Archive (find + download music)
  FFmpeg  — precise trim, 9:16, concat, mix music, burn subs
  → returns reel.mp4 + X-Caption header
"""

import asyncio
import json
import logging
import os
import time

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from agents.flows            import run_reel_flow
from agents.key_manager      import has_keys, key_count
from services.subtitle       import generate_ass_subtitles, burn_subtitles, get_video_duration
from services.video_editor   import produce_reel
from services.audio_master   import mix_with_ducking
from services.music_selector import mix_music
from services.gcs_upload     import upload_and_get_signed_url
from utils.file_handler      import TempFileHandler

logger     = logging.getLogger(__name__)
router     = APIRouter()
MAX_MB     = 500
MAX_TOTAL_DURATION_SEC = 300  # 5 minutes


@router.get("/reel-pipeline/status")
async def pipeline_status():
    logger.info("[PIPELINE] GET /reel-pipeline/status")
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


@router.post("/reel-pipeline")
async def process_reel_pipeline(
    background_tasks: BackgroundTasks,
    videos: list[UploadFile] = File(...),
):
    """
    Upload raw clips → AI pipeline → one finished reel.mp4
    Caption is returned in X-Caption response header (JSON encoded).
    """
    logger.info(f"[PIPELINE] POST /reel-pipeline | videos={len(videos)}")
    if not videos:
        raise HTTPException(status_code=400, detail="No videos uploaded")

    handler = TempFileHandler()
    wall    = time.time()

    try:
        # ── 1. Save uploads ────────────────────────────────────────────
        logger.info(f"[PIPELINE] Step 1: Saving {len(videos)} uploads...")
        clip_paths, total_bytes = [], 0
        for v in videos:
            content      = await v.read()
            total_bytes += len(content)
            if total_bytes > MAX_MB * 1024 * 1024:
                raise HTTPException(status_code=400, detail=f"Total upload must be under {MAX_MB}MB")
            ext = os.path.splitext(v.filename or ".mp4")[1] or ".mp4"
            clip_paths.append(handler.save_upload(content, ext))
        logger.info(f"[PIPELINE] Step 1 done: Saved {total_bytes/1024/1024:.1f}MB | paths={[p.name for p in clip_paths]}")

        # ── 1b. Validate total duration ─────────────────────────────────
        total_duration = sum(get_video_duration(p) for p in clip_paths)
        if total_duration > MAX_TOTAL_DURATION_SEC:
            raise HTTPException(
                status_code=400,
                detail=f"Total duration must be under 5 minutes (current: {total_duration:.1f}s)",
            )

        # ── 2. Run CrewAI Flow (6-step AI pipeline) ────────────────────
        # Run in thread: CrewAI uses asyncio.run() which cannot run inside FastAPI's event loop
        logger.info("[PIPELINE] Step 2: Starting 4-agent AI pipeline...")
        t_ai     = time.time()
        blueprint = await asyncio.to_thread(run_reel_flow, clip_paths)
        logger.info(f"[PIPELINE] Step 2 done: AI pipeline in {time.time()-t_ai:.1f}s | clips={len(blueprint.get('ordered_clips', []))} | words={len(blueprint.get('all_words', []))}")

        ordered_clips  = blueprint["ordered_clips"]
        subtitle_style = blueprint["subtitle_style"]
        music_path     = blueprint["music_path"]
        all_words      = blueprint["all_words"]
        caption        = blueprint["caption"]
        edit_plan      = blueprint["edit_plan"]

        if not ordered_clips:
            logger.error("[PIPELINE] Brain cut all clips — no content to produce")
            raise HTTPException(400, "Brain decided all clips should be cut — please upload better content")

        # ── 3. FFmpeg: trim + reframe + concat ─────────────────────────
        t_edit   = time.time()
        logger.info(f"[PIPELINE] Step 3: Producing reel: {len(ordered_clips)} clips | style={subtitle_style} | music={'yes' if music_path else 'fallback'}")
        stitched = handler.create_temp_path(".mp4")
        produce_reel(ordered_clips, stitched)
        for item in ordered_clips:
            handler.cleanup_file(item[0])
        logger.info(f"[PIPELINE] Step 3 done: Reel produced in {time.time()-t_edit:.1f}s")

        # ── 4. Mix music (with ducking when speech present) ──────────────
        with_music = handler.create_temp_path(".mp4")
        if music_path and music_path.exists():
            logger.info("[PIPELINE] Mixing music with ducking...")
            mix_with_ducking(
                stitched, music_path, all_words, with_music,
                music_volume=float(edit_plan.get("music_volume", 0.12)),
                duck_strength=edit_plan.get("duck_strength", "medium"),
                fade_in=float(edit_plan.get("music_fade_in_sec", 1.0)),
                fade_out=float(edit_plan.get("music_fade_out_sec", 2.0)),
            )
            music_path.unlink(missing_ok=True)
        else:
            logger.info(f"[PIPELINE] No downloaded music — using bundled fallback (mood={edit_plan.get('music_mood','motivational')})")
            mix_music(stitched, with_music, mood=edit_plan.get("music_mood", "motivational"))
        handler.cleanup_file(stitched)

        # ── 5. Burn subtitles (using Brain's pre-computed word list) ───
        t_subs = time.time()
        logger.info(f"[PIPELINE] Step 5: Burning subtitles | words={len(all_words)} | style={subtitle_style}")
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
        logger.info(f"[PIPELINE] Caption hook: \"{caption.get('hook','')}\" | CTA: \"{caption.get('cta','')}\"")

        gcs_bucket = os.environ.get("GCS_BUCKET")
        if gcs_bucket:
            # Upload to GCS, return JSON with signed URL (2h expiry; bucket lifecycle deletes after 24h)
            download_url = upload_and_get_signed_url(final, gcs_bucket)
            background_tasks.add_task(handler.cleanup_file, final)
            return JSONResponse(
                content={
                    "download_url": download_url,
                    "caption": caption,
                    "subtitle_style": subtitle_style,
                    "music_mood": edit_plan.get("music_mood", ""),
                }
            )

        # Local dev: return file directly (no 32MB limit locally)
        caption_header = json.dumps(caption, ensure_ascii=False)
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
    except FileNotFoundError:
        logger.error("[PIPELINE ERROR] FFmpeg/ffprobe not found")
        handler.cleanup()
        raise HTTPException(
            500,
            "FFmpeg not found. Install from https://ffmpeg.org/download.html and add the bin folder to your PATH."
        )
    except OSError as e:
        if e.errno == 2:
            logger.error("[PIPELINE ERROR] FFmpeg/ffprobe not found")
            handler.cleanup()
            raise HTTPException(
                500,
                "FFmpeg not found. Install from https://ffmpeg.org/download.html and add the bin folder to your PATH."
            )
        handler.cleanup()
        raise
    except Exception as e:
        logger.error(f"[PIPELINE ERROR] {e}", exc_info=True)
        handler.cleanup()
        raise HTTPException(500, f"Pipeline failed: {str(e)}")

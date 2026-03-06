from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response
import os
import time
import logging
import zipfile
import io
from pathlib import Path

from services.transcription import transcription_service
from services.subtitle import generate_ass_subtitles, burn_subtitles, extract_audio, SUBTITLE_STYLES
from services.subtitle import copy_video, get_video_duration
from utils.file_handler import TempFileHandler

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_TOTAL_SIZE_MB = 500
MAX_TOTAL_DURATION_SEC = 300  # 5 minutes


@router.post("/process")
async def process_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    style: str = Form("hormozi")
):
    """
    Process uploaded video:
    1. Extract audio
    2. Transcribe with Whisper
    3. Generate word-by-word subtitles
    4. Burn subtitles onto video
    5. Return processed video
    """
    logger.info(f"[VIDEO] POST /process | file={video.filename} | style={style} | content_type={video.content_type}")
    ct = (video.content_type or "").lower()
    if ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Photos are not supported. Please upload a video (MP4, WebM, etc.).")
    if not ct or not ct.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")

    file_handler = TempFileHandler()
    total_start = time.time()

    try:
        # Step 1: Save uploaded video
        step_start = time.time()
        logger.info(f"[STEP 1/5] Saving uploaded video: {video.filename}")
        video_content = await video.read()
        video_ext = os.path.splitext(video.filename or ".mp4")[1]
        video_path = file_handler.save_upload(video_content, video_ext)
        file_size_mb = len(video_content) / (1024 * 1024)
        logger.info(f"[STEP 1/5] DONE - Saved {file_size_mb:.2f}MB ({len(video_content)} bytes) in {time.time() - step_start:.2f}s")

        duration = get_video_duration(video_path)
        if duration > MAX_TOTAL_DURATION_SEC:
            file_handler.cleanup_file(video_path)
            raise HTTPException(
                status_code=400,
                detail=f"Video must be under 5 minutes (current: {duration:.1f}s)"
            )

        # Step 2: Extract audio
        step_start = time.time()
        logger.info("[STEP 2/5] Extracting audio with FFmpeg...")
        audio_path = file_handler.create_temp_path(".wav")
        extract_audio(video_path, audio_path)
        logger.info(f"[STEP 2/5] DONE - Audio extracted in {time.time() - step_start:.2f}s")

        # Step 3: Transcribe with Groq Whisper Large v3 (cloud)
        step_start = time.time()
        logger.info("[STEP 3/5] Transcribing with Groq Whisper Large v3...")
        words = transcription_service.transcribe(audio_path)
        logger.info(f"[STEP 3/5] DONE - {len(words)} words transcribed in {time.time() - step_start:.2f}s")

        if not words:
            logger.error("[STEP 3/5] FAILED - No speech detected in video")
            raise HTTPException(
                status_code=400,
                detail="No speech detected in video"
            )

        # Step 4: Generate subtitles with selected style
        step_start = time.time()
        style_name = SUBTITLE_STYLES.get(style, {}).get("name", style)
        logger.info(f"[STEP 4/5] Generating ASS subtitles ({style_name}) for {len(words)} words...")
        subtitle_path = file_handler.create_temp_path(".ass")
        generate_ass_subtitles(words, subtitle_path, style=style)
        logger.info(f"[STEP 4/5] DONE - Subtitles generated in {time.time() - step_start:.2f}s")

        # Step 5: Burn subtitles onto video
        step_start = time.time()
        logger.info("[STEP 5/5] Burning subtitles onto video with FFmpeg (ultrafast preset)...")
        output_path = file_handler.create_temp_path(".mp4")
        burn_subtitles(video_path, subtitle_path, output_path)
        output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"[STEP 5/5] DONE - Video rendered ({output_size_mb:.2f}MB) in {time.time() - step_start:.2f}s")

        # Clean up intermediate files but keep output
        file_handler.cleanup_file(video_path)
        file_handler.cleanup_file(audio_path)
        file_handler.cleanup_file(subtitle_path)

        total_time = time.time() - total_start
        logger.info(f"[SUCCESS] Total processing time: {total_time:.2f}s | output={output_size_mb:.2f}MB")

        # Return the processed video; cleanup after response is sent
        background_tasks.add_task(file_handler.cleanup_file, output_path)
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename="subtitled_video.mp4",
        )

    except HTTPException:
        logger.error(f"[ERROR] HTTPException after {time.time() - total_start:.2f}s")
        file_handler.cleanup()
        raise
    except FileNotFoundError as e:
        logger.error(f"[ERROR] FileNotFoundError: {e}")
        file_handler.cleanup()
        raise HTTPException(
            status_code=500,
            detail="FFmpeg not found. Install from https://ffmpeg.org/download.html and add the bin folder to your PATH."
        )
    except OSError as e:
        if e.errno == 2:  # ENOENT - file not found
            logger.error(f"[ERROR] FFmpeg/ffprobe not found: {e}")
            file_handler.cleanup()
            raise HTTPException(
                status_code=500,
                detail="FFmpeg not found. Install from https://ffmpeg.org/download.html and add the bin folder to your PATH."
            )
        file_handler.cleanup()
        raise
    except Exception as e:
        logger.error(f"[ERROR] Processing failed after {time.time() - total_start:.2f}s: {str(e)}")
        file_handler.cleanup()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/process-reel")
async def process_reel(
    background_tasks: BackgroundTasks,
    videos: list[UploadFile] = File(...),
    style: str = Form("hormozi")
):
    """
    Process one video (subtitles only). Only 1 video allowed.
    """
    if len(videos) != 1:
        raise HTTPException(
            status_code=400,
            detail="Only 1 video allowed. Please upload a single video.",
        )
    logger.info(f"[VIDEO] POST /process-reel | count={len(videos)} | style={style}")

    video_contents: list[tuple[str, bytes]] = []
    total_size = 0
    for i, v in enumerate(videos):
        ct = (v.content_type or "").lower()
        if ct.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"Photos are not supported. '{v.filename or 'file'}' appears to be an image. Please upload videos only.")
        if not ct or not ct.startswith("video/"):
            raise HTTPException(status_code=400, detail=f"File must be a video: {v.filename}")
        key = v.filename or f"video_{i}.mp4"
        content = await v.read()
        video_contents.append((key, content))
        total_size += len(content)

    if total_size > MAX_TOTAL_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"Total size must be under {MAX_TOTAL_SIZE_MB}MB"
        )

    file_handler = TempFileHandler()

    # Check total duration (must save files first to probe)
    total_duration = 0.0
    for key, content in video_contents:
        video_ext = os.path.splitext(key)[1]
        temp_path = file_handler.save_upload(content, video_ext)
        try:
            total_duration += get_video_duration(temp_path)
        finally:
            file_handler.cleanup_file(temp_path)

    if total_duration > MAX_TOTAL_DURATION_SEC:
        raise HTTPException(
            status_code=400,
            detail=f"Total duration must be under 5 minutes (current: {total_duration:.1f}s)"
        )
    total_start = time.time()
    processed_paths: list[tuple[str, Path]] = []

    try:
        for i, (key, content) in enumerate(video_contents):
            step_start = time.time()
            base_name = Path(key).stem
            video_ext = os.path.splitext(key)[1] or ".mp4"

            logger.info(f"[{i+1}/{len(videos)}] Processing: {key}")

            video_path = file_handler.save_upload(content, video_ext)
            audio_path = file_handler.create_temp_path(".wav")
            extract_audio(video_path, audio_path)

            words = transcription_service.transcribe(audio_path)
            output_path = file_handler.create_temp_path(".mp4")
            if not words:
                logger.warning(f"[{i+1}/{len(video_contents)}] No speech in {key}, copying without subtitles")
                copy_video(video_path, output_path)
            else:
                subtitle_path = file_handler.create_temp_path(".ass")
                generate_ass_subtitles(words, subtitle_path, style=style)
                burn_subtitles(video_path, subtitle_path, output_path)
                file_handler.cleanup_file(subtitle_path)

            file_handler.cleanup_file(video_path)
            file_handler.cleanup_file(audio_path)

            out_name = f"{base_name}_subtitled.mp4"
            processed_paths.append((out_name, output_path))
            logger.info(f"[{i+1}/{len(videos)}] DONE in {time.time() - step_start:.2f}s")

        total_time = time.time() - total_start
        logger.info(f"[SUCCESS] Processed {len(video_contents)} video(s) in {total_time:.2f}s")

        # Single video: return file directly
        out_name, output_path = processed_paths[0]
        background_tasks.add_task(file_handler.cleanup_file, output_path)
        return FileResponse(
            path=str(output_path),
            media_type="video/mp4",
            filename=out_name,
            background=background_tasks,
        )

    except HTTPException:
        file_handler.cleanup()
        raise
    except FileNotFoundError:
        logger.error("[ERROR] FFmpeg/ffprobe not found")
        file_handler.cleanup()
        raise HTTPException(
            status_code=500,
            detail="FFmpeg not found. Install from https://ffmpeg.org/download.html and add the bin folder to your PATH."
        )
    except OSError as e:
        if e.errno == 2:
            logger.error("[ERROR] FFmpeg/ffprobe not found")
            file_handler.cleanup()
            raise HTTPException(
                status_code=500,
                detail="FFmpeg not found. Install from https://ffmpeg.org/download.html and add the bin folder to your PATH."
            )
        raise
    except Exception as e:
        logger.error(f"[ERROR] Batch processing failed: {str(e)}")
        file_handler.cleanup()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


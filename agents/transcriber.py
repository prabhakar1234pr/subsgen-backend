"""
agents/transcriber.py

Agent 1 — Transcriber
Uses Groq Whisper Large v3 to transcribe each clip with word-level timestamps.
Returns rich transcript data used by the Brain agent.
"""

import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-large-v3"          # accurate, free on Groq
MAX_AUDIO_MB  = 25                          # Groq limit is 25MB per request


def _extract_audio_for_groq(video_path: Path) -> Path:
    """
    Extract audio as mono 16kHz MP3 (small file size for API upload).
    Groq Whisper accepts mp3, mp4, wav, webm etc.
    """
    out = Path(tempfile.gettempdir()) / f"{uuid.uuid4()}.mp3"
    subprocess.run([
        "ffmpeg", "-i", str(video_path),
        "-vn",                    # no video
        "-acodec", "libmp3lame",
        "-ar", "16000",           # 16kHz
        "-ac", "1",               # mono
        "-b:a", "64k",            # low bitrate = small file
        "-y", str(out),
    ], check=True, capture_output=True)
    return out


def _compress_if_needed(audio_path: Path) -> Path:
    """If audio file > 25MB, re-compress harder."""
    size_mb = audio_path.stat().st_size / 1024 / 1024
    if size_mb <= MAX_AUDIO_MB:
        return audio_path

    logger.warning(f"Audio {size_mb:.1f}MB > {MAX_AUDIO_MB}MB limit, recompressing...")
    out = Path(tempfile.gettempdir()) / f"{uuid.uuid4()}.mp3"
    subprocess.run([
        "ffmpeg", "-i", str(audio_path),
        "-acodec", "libmp3lame",
        "-ar", "16000", "-ac", "1",
        "-b:a", "32k",
        "-y", str(out),
    ], check=True, capture_output=True)
    audio_path.unlink(missing_ok=True)
    return out


def transcribe_clip(video_path: Path, clip_index: int = 0) -> dict:
    """
    Transcribe a single video clip using Groq Whisper Large v3.

    Returns:
    {
        "clip_index": int,
        "clip_name": str,
        "full_text": str,
        "duration_sec": float,
        "words": [{"word": str, "start": float, "end": float}, ...],
        "segments": [{"text": str, "start": float, "end": float}, ...],
        "language": str,
        "speech_ratio": float,   # fraction of clip that has speech (0-1)
        "has_speech": bool,
    }
    """
    audio_path = None
    try:
        # Get video duration
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=True
        )
        duration = float(result.stdout.strip())

        if not has_keys():
            logger.warning("No Groq keys — returning empty transcript")
            return _empty_transcript(clip_index, video_path.name, duration)

        # Extract + compress audio
        logger.info(f"[Transcriber] Clip {clip_index+1}: Extracting audio from {video_path.name} | duration={duration:.1f}s")
        audio_path = _extract_audio_for_groq(video_path)
        audio_path = _compress_if_needed(audio_path)

        size_mb = audio_path.stat().st_size / 1024 / 1024
        logger.info(f"[Transcriber] Clip {clip_index+1}: Audio ready {size_mb:.1f}MB, sending to Groq Whisper Large v3...")

        client = Groq(api_key=next_key())

        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=f,
                response_format="verbose_json",   # includes word timestamps
                timestamp_granularities=["word", "segment"],
                language="en",
            )

        # Parse response
        full_text = response.text.strip()
        words = []
        if hasattr(response, "words") and response.words:
            for w in response.words:
                words.append({
                    "word":  w.word.strip(),
                    "start": round(float(w.start), 3),
                    "end":   round(float(w.end), 3),
                })

        segments = []
        if hasattr(response, "segments") and response.segments:
            for s in response.segments:
                segments.append({
                    "text":  s.text.strip(),
                    "start": round(float(s.start), 3),
                    "end":   round(float(s.end), 3),
                })

        # Calculate speech ratio
        speech_duration = sum(
            s["end"] - s["start"] for s in segments
        ) if segments else (duration * 0.7 if full_text else 0)
        speech_ratio = min(1.0, speech_duration / duration) if duration > 0 else 0

        logger.info(
            f"[Transcriber] Clip {clip_index+1}: {len(words)} words, "
            f"speech_ratio={speech_ratio:.0%}, lang={getattr(response, 'language', 'en')}"
        )

        return {
            "clip_index":   clip_index,
            "clip_name":    video_path.name,
            "full_text":    full_text,
            "duration_sec": duration,
            "words":        words,
            "segments":     segments,
            "language":     getattr(response, "language", "en"),
            "speech_ratio": speech_ratio,
            "has_speech":   bool(full_text.strip()),
        }

    except Exception as e:
        logger.error(f"[Transcriber] Clip {clip_index+1} failed: {e}")
        duration = 0.0
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True)
            duration = float(r.stdout.strip())
        except Exception:
            pass
        return _empty_transcript(clip_index, video_path.name, duration)

    finally:
        if audio_path and audio_path.exists():
            audio_path.unlink(missing_ok=True)


def _empty_transcript(clip_index: int, clip_name: str, duration: float) -> dict:
    return {
        "clip_index":   clip_index,
        "clip_name":    clip_name,
        "full_text":    "",
        "duration_sec": duration,
        "words":        [],
        "segments":     [],
        "language":     "en",
        "speech_ratio": 0.0,
        "has_speech":   False,
    }

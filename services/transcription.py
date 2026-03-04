"""
Transcription service using Groq Whisper Large v3 (cloud).
Same API as reel pipeline — no local model, lower memory.
"""

import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException
from groq import Groq

from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-large-v3"
MAX_AUDIO_MB = 25  # Groq limit


def _to_mp3_if_needed(audio_path: Path) -> Path:
    """Convert to MP3 if over 25MB for Groq upload."""
    size_mb = audio_path.stat().st_size / 1024 / 1024
    if size_mb <= MAX_AUDIO_MB:
        return audio_path

    logger.warning(f"Audio {size_mb:.1f}MB > {MAX_AUDIO_MB}MB, compressing to MP3...")
    out = Path(tempfile.gettempdir()) / f"{uuid.uuid4()}.mp3"
    subprocess.run([
        "ffmpeg", "-i", str(audio_path),
        "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        "-y", str(out),
    ], check=True, capture_output=True)
    return out


def transcribe(audio_path: Path) -> list[dict]:
    """
    Transcribe audio using Groq Whisper Large v3 (cloud).
    Returns list of {"word": str, "start": float, "end": float}.
    """
    if not has_keys():
        logger.warning("[TRANSCRIPTION] No Groq keys — cannot transcribe")
        raise HTTPException(
            status_code=503,
            detail="Groq API key required. Add GROQ_API_KEY to environment.",
        )

    upload_path = _to_mp3_if_needed(audio_path)
    cleanup_upload = upload_path != audio_path

    try:
        logger.info("[TRANSCRIPTION] Sending to Groq Whisper Large v3...")
        client = Groq(api_key=next_key())

        with open(upload_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                language="en",
            )

        words = []
        if hasattr(response, "words") and response.words:
            for w in response.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                })

        logger.info(f"[TRANSCRIPTION] {len(words)} words from Groq Whisper")
        return words

    except Exception as e:
        logger.error(f"[TRANSCRIPTION] Groq failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Transcription failed: {str(e)}",
        )
    finally:
        if cleanup_upload and upload_path.exists():
            upload_path.unlink(missing_ok=True)


# Backward compat: service-like interface for video router
class TranscriptionService:
    """Wrapper for Groq Whisper (cloud) — same interface as before."""

    def transcribe(self, audio_path: Path) -> list[dict]:
        return transcribe(audio_path)


transcription_service = TranscriptionService()

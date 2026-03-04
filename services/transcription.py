from faster_whisper import WhisperModel
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Handles audio transcription using faster-whisper (optimized Whisper)."""

    def __init__(self, model_name: str = "tiny"):
        self.model = None
        self.model_name = model_name

    def load_model(self):
        """Load faster-whisper model (lazy loading to save memory)."""
        if self.model is None:
            logger.info(f"[TRANSCRIPTION] Loading faster-whisper model: {self.model_name}")
            # Use CPU with int8 quantization for speed
            self.model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",  # Faster on CPU
            )
            logger.info("[TRANSCRIPTION] Model loaded successfully")

    def transcribe(self, audio_path: Path) -> list[dict]:
        """
        Transcribe audio file and return word-level timestamps.
        English only for faster processing.
        
        Returns:
            List of word dicts with 'word', 'start', 'end' keys
        """
        self.load_model()

        segments, info = self.model.transcribe(
            str(audio_path),
            language="en",
            word_timestamps=True,
            beam_size=1,  # Faster decoding
            best_of=1,    # Faster decoding
            vad_filter=True,  # Skip silence - faster
        )

        # Extract words from segments
        words = []
        for segment in segments:
            if segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word.strip(),
                        "start": word.start,
                        "end": word.end,
                    })

        return words


# Global instance for reuse - using tiny model for speed
transcription_service = TranscriptionService(model_name="tiny")

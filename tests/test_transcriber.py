"""
tests/test_transcriber.py

E2E tests for Transcriber agent (Agent 1).
"""

import pytest
from pathlib import Path

from agents.transcriber import transcribe_clip


class TestTranscriber:
    """Transcriber agent E2E tests."""

    def test_transcribe_clip_returns_full_transcript(
        self, sample_video_path, mock_key_manager, mock_subprocess, mock_groq
    ):
        """Transcriber produces transcript with words and segments."""
        result = transcribe_clip(sample_video_path, clip_index=0)

        assert result["clip_index"] == 0
        assert result["clip_name"] == "test_clip.mp4"
        assert result["full_text"] == "This is a test transcript for the reel."
        assert result["duration_sec"] == 15.0
        assert result["has_speech"] is True
        assert result["language"] == "en"
        assert len(result["words"]) == 8
        assert result["words"][0]["word"] == "This"
        assert result["words"][0]["start"] == 0.0
        assert result["words"][0]["end"] == 0.3
        assert len(result["segments"]) >= 1

    def test_transcribe_clip_raises_without_api_keys(
        self, sample_video_path, mock_subprocess
    ):
        """Transcriber raises when no Groq keys available."""
        with pytest.raises(RuntimeError, match="No Groq API keys"):
            transcribe_clip(sample_video_path, clip_index=0)

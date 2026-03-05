"""
tests/test_subtitle_verifier.py

E2E tests for SubtitleVerifier agent (Agent 6).
"""

import pytest

from agents.subtitle_verifier import verify_and_decide


class TestSubtitleVerifier:
    """SubtitleVerifier agent E2E tests."""

    def test_verify_returns_needs_subtitles_and_style(
        self, sample_transcripts, sample_edit_plan, mock_key_manager, mock_groq
    ):
        """SubtitleVerifier returns needs_subtitles and subtitle_style."""
        all_words = [
            {"word": "This", "start": 0.0, "end": 0.3},
            {"word": "is", "start": 0.3, "end": 0.5},
            {"word": "test", "start": 0.5, "end": 1.0},
        ]
        result = verify_and_decide(all_words, sample_edit_plan, sample_transcripts)

        assert "needs_subtitles" in result
        assert "subtitle_style" in result
        assert result["subtitle_style"] in ("hormozi", "minimal", "neon", "fire", "karaoke", "purple")

    def test_verify_raises_without_api_keys(
        self, sample_transcripts, sample_edit_plan
    ):
        """SubtitleVerifier raises when no Groq keys available."""
        with pytest.raises(RuntimeError, match="No Groq API keys"):
            verify_and_decide([], sample_edit_plan, sample_transcripts)

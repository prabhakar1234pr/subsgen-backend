"""
tests/test_holistic_reviewer.py

E2E tests for HolisticReviewer agent.
"""

import pytest

from agents.holistic_reviewer import create_holistic_review


class TestHolisticReviewer:
    """HolisticReviewer agent E2E tests."""

    def test_create_holistic_review_returns_review(
        self, sample_transcripts, sample_analyses,
        mock_key_manager, mock_groq
    ):
        """HolisticReviewer produces structured review."""
        result = create_holistic_review(sample_transcripts, sample_analyses)

        assert "overall_impression" in result
        assert "best_clip_for_hook" in result
        assert "best_clip_for_cta" in result
        assert "clips_to_cut" in result
        assert "pacing_suggestion" in result
        assert "creative_notes" in result
        assert 0 <= result["best_clip_for_hook"] < len(sample_transcripts)
        assert 0 <= result["best_clip_for_cta"] < len(sample_transcripts)

    def test_create_holistic_review_empty_clips_returns_minimal(
        self, mock_key_manager, mock_groq
    ):
        """HolisticReviewer returns minimal structure for 0 clips."""
        result = create_holistic_review([], [])

        assert result["overall_impression"] == ""
        assert result["best_clip_for_hook"] == 0
        assert result["best_clip_for_cta"] == 0
        assert result["clips_to_cut"] == []

    def test_create_holistic_review_raises_without_api_keys(
        self, sample_transcripts, sample_analyses
    ):
        """HolisticReviewer raises when no Groq keys available."""
        with pytest.raises(RuntimeError, match="No Groq API keys"):
            create_holistic_review(sample_transcripts, sample_analyses)

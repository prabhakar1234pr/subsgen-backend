"""
tests/test_video_analyst.py

E2E tests for VideoAnalyst agent (Agent 2).
"""

import pytest
from pathlib import Path

from agents.video_analyst import analyze_clip


class TestVideoAnalyst:
    """VideoAnalyst agent E2E tests."""

    def test_analyze_clip_returns_visual_analysis(
        self, sample_video_path, sample_transcripts,
        mock_key_manager, mock_subprocess, mock_groq
    ):
        """VideoAnalyst produces visual analysis with required fields."""
        transcript = sample_transcripts[0]
        result = analyze_clip(sample_video_path, transcript=transcript, clip_index=0)

        assert result["clip_index"] == 0
        assert result["clip_name"] == "test_clip.mp4"
        assert result["content_type"] == "talking_head"
        assert result["visual_quality"] in ("poor", "decent", "good", "excellent")
        assert 1 <= result["visual_hook_strength"] <= 10
        assert 1 <= result["overall_visual_score"] <= 10
        assert result["recommended_subtitle_style"] in (
            "hormozi", "minimal", "neon", "fire", "karaoke", "purple"
        )

    def test_analyze_clip_raises_without_api_keys(
        self, sample_video_path, sample_transcripts, mock_subprocess
    ):
        """VideoAnalyst raises when no Groq keys available."""
        with pytest.raises(RuntimeError, match="No Groq API keys"):
            analyze_clip(
                sample_video_path,
                transcript=sample_transcripts[0],
                clip_index=0,
            )

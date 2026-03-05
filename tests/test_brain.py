"""
tests/test_brain.py

E2E tests for EditDirector (Brain) agent (Agent 3).
"""

import pytest

from agents.brain import create_edit_plan


class TestBrain:
    """EditDirector (Brain) agent E2E tests."""

    def test_create_edit_plan_returns_complete_plan(
        self, sample_transcripts, sample_analyses,
        mock_key_manager, mock_groq
    ):
        """Brain produces complete edit plan with all required fields."""
        result = create_edit_plan(
            sample_transcripts,
            sample_analyses,
            holistic_review={"overall_impression": "Strong content.", "pacing_suggestion": "normal", "creative_notes": ""},
        )

        assert "clips" in result
        assert len(result["clips"]) >= 1
        clip = result["clips"][0]
        assert "clip_index" in clip
        assert "keep" in clip
        assert "trim_start_sec" in clip
        assert "trim_end_sec" in clip
        assert "transition_in" in clip
        assert "transition_out" in clip
        assert "transition_duration_sec" in clip
        assert "clips" in result
        assert "music_volume" in result
        assert "duck_strength" in result
        assert "music_fade_in_sec" in result
        assert "music_fade_out_sec" in result
        assert "caption" in result
        assert "hook" in result["caption"]
        assert "body" in result["caption"]
        assert "cta" in result["caption"]

    def test_create_edit_plan_clamps_trim_to_clip_duration(
        self, sample_transcripts, sample_analyses,
        mock_key_manager, mock_groq
    ):
        """Brain clamps trim times to physical clip bounds."""
        result = create_edit_plan(sample_transcripts, sample_analyses)

        clip = result["clips"][0]
        dur = sample_transcripts[0]["duration_sec"]
        assert 0 <= clip["trim_start_sec"] <= dur
        assert 0 <= clip["trim_end_sec"] <= dur

    def test_create_edit_plan_raises_without_api_keys(
        self, sample_transcripts, sample_analyses
    ):
        """Brain raises when no Groq keys available."""
        with pytest.raises(RuntimeError, match="No Groq API keys"):
            create_edit_plan(sample_transcripts, sample_analyses)

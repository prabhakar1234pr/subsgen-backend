"""
tests/test_reel_flow_e2e.py

End-to-end tests for the full ReelFlow pipeline (all 5 agents).
"""

import pytest
from pathlib import Path

from agents.flows.reel_flow import run_reel_flow


class TestReelFlowE2E:
    """Full pipeline E2E tests."""

    def test_run_reel_flow_produces_blueprint(
        self, sample_video_path, all_mocks
    ):
        """Full pipeline produces valid ReelBlueprint."""
        clip_paths = [sample_video_path]
        blueprint = run_reel_flow(clip_paths)

        assert "ordered_clips" in blueprint
        assert "edit_plan" in blueprint
        assert "transcripts" in blueprint
        assert "subtitle_style" in blueprint
        assert "caption" in blueprint
        assert "all_words" in blueprint
        assert "music_path" in blueprint
        assert "color_preset" in blueprint

        assert "needs_subtitles" in blueprint
        assert len(blueprint["transcripts"]) == 1
        assert len(blueprint["edit_plan"]["clips"]) >= 1
        assert blueprint["subtitle_style"] in ("hormozi", "minimal", "neon", "fire", "karaoke", "purple")
        assert "hook" in blueprint["caption"]

    def test_run_reel_flow_ordered_clips_have_required_fields(
        self, sample_video_path, all_mocks
    ):
        """Ordered clips contain path, trim, transition_out, transition_duration."""
        blueprint = run_reel_flow([sample_video_path])
        ordered = blueprint["ordered_clips"]

        assert len(ordered) >= 1
        for item in ordered:
            assert len(item) == 5
            path, trim_start, trim_end, trans_out, trans_dur = item
            assert path.exists()
            assert isinstance(trim_start, (int, float))
            assert isinstance(trim_end, (int, float))
            assert trans_out in (
                "none", "fade", "wipeleft", "wiperight", "wipeup", "wipedown",
                "slideleft", "slideright", "slideup", "slidedown",
                "rectcrop", "distance", "fadeblack", "fadewhite",
            )
            assert trans_dur > 0

    def test_run_reel_flow_all_words_have_timestamps(
        self, sample_video_path, all_mocks
    ):
        """all_words has word, start, end for subtitles."""
        blueprint = run_reel_flow([sample_video_path])
        words = blueprint["all_words"]

        for w in words:
            assert "word" in w
            assert "start" in w
            assert "end" in w
            assert w["start"] <= w["end"]

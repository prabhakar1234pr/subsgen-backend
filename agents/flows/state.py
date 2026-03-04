"""
agents/flows/state.py

ReelFlowState — Pydantic state schema for the CrewAI Flow.
Holds all data passed between flow steps.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ReelFlowState(BaseModel):
    """State passed through the ReelFlow pipeline."""

    clip_paths: list[Path] = Field(default_factory=list, description="Paths to raw video clips")
    transcripts: list[dict[str, Any]] = Field(default_factory=list, description="Per-clip transcripts")
    analyses: list[dict[str, Any]] = Field(default_factory=list, description="Per-clip visual analyses")
    holistic_review: dict[str, Any] = Field(default_factory=dict, description="Human-like holistic review")
    edit_plan: dict[str, Any] = Field(default_factory=dict, description="Edit plan from Brain/EditDirector")
    music_path: Path | None = Field(default=None, description="Path to downloaded music")
    stitched_path: Path | None = Field(default=None, description="Path to stitched video (pre-music)")
    final_path: Path | None = Field(default=None, description="Path to final reel")

    model_config = {"arbitrary_types_allowed": True}

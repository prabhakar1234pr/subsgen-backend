"""
agents/schemas.py

Pydantic schemas for the AI reel pipeline.
"""

from typing import Any


def ensure_clip_edit_fields(clip: dict) -> dict:
    """Ensure clip has agent-driven transition fields (backward compat)."""
    clip.setdefault("transition_in", "fade")
    clip.setdefault("transition_out", "fade")
    clip.setdefault("transition_duration_sec", 0.35)
    clip.setdefault("pacing_note", "normal")
    return clip


def ensure_edit_plan_fields(plan: dict) -> dict:
    """Ensure edit plan has agent-driven mix/creative fields."""
    plan.setdefault("creative_direction", "smooth flow")
    plan.setdefault("music_volume", 0.12)
    plan.setdefault("duck_strength", "medium")
    plan.setdefault("music_fade_in_sec", 1.0)
    plan.setdefault("music_fade_out_sec", 2.0)
    plan.setdefault("music_creative_brief", "")
    return plan

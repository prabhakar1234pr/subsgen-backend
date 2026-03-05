"""
tests/conftest.py

Comprehensive mock setup for end-to-end agent testing.
Mocks: Groq API, httpx (Internet Archive), subprocess (ffmpeg/ffprobe), key_manager.
"""

import base64
import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Minimal valid JPEG (1x1 pixel) for VideoAnalyst frame extraction mock
# ─────────────────────────────────────────────────────────────────────────────
MINIMAL_JPEG_BYTES = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x24, 0x24, 0x2E, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2E,
    0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C,
    0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00,
    0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01,
    0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
    0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
    0xFB, 0xD8, 0xE8, 0xB4, 0xFF, 0xD9,
])


# ─────────────────────────────────────────────────────────────────────────────
# Sample data for mock responses
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_TRANSCRIPT = {
    "clip_index": 0,
    "clip_name": "test_clip.mp4",
    "full_text": "This is a test transcript for the reel.",
    "duration_sec": 15.0,
    "words": [
        {"word": "This", "start": 0.0, "end": 0.3},
        {"word": "is", "start": 0.3, "end": 0.5},
        {"word": "a", "start": 0.5, "end": 0.6},
        {"word": "test", "start": 0.6, "end": 1.0},
        {"word": "transcript", "start": 1.0, "end": 1.5},
        {"word": "for", "start": 1.5, "end": 1.7},
        {"word": "the", "start": 1.7, "end": 1.9},
        {"word": "reel.", "start": 1.9, "end": 2.2},
    ],
    "segments": [{"text": "This is a test transcript for the reel.", "start": 0.0, "end": 2.2}],
    "language": "en",
    "speech_ratio": 0.15,
    "has_speech": True,
}

SAMPLE_ANALYSIS = {
    "clip_index": 0,
    "clip_name": "test_clip.mp4",
    "content_type": "talking_head",
    "subject_description": "person speaking to camera",
    "setting": "indoor_plain",
    "speaker_energy": "medium",
    "speaker_confidence": "high",
    "lighting_quality": "good",
    "framing": "medium",
    "visual_quality": "good",
    "dominant_colors": ["neutral", "warm"],
    "recommended_subtitle_style": "hormozi",
    "subtitle_style_reason": "High contrast for talking head",
    "visual_hook_strength": 7,
    "overall_visual_score": 8,
}

SAMPLE_HOLISTIC_REVIEW = {
    "overall_impression": "Strong talking head content with clear speech.",
    "best_clip_for_hook": 0,
    "best_clip_for_cta": 0,
    "clips_to_cut": [],
    "pacing_suggestion": "normal",
    "creative_notes": "Consider punchy cuts.",
}

SAMPLE_EDIT_PLAN = {
    "clips": [
        {
            "clip_index": 0,
            "keep": True,
            "keep_score": 8,
            "keep_reason": "strong hook",
            "narrative_role": "hook",
            "narrative_order": 0,
            "trim_start_sec": 0.5,
            "trim_end_sec": 14.0,
            "trim_reason": "skip filler",
            "transition_in": "fade",
            "transition_out": "fade",
            "transition_duration_sec": 0.35,
            "pacing_note": "normal",
        }
    ],
    "overall_mood": "motivational",
    "overall_energy": "medium",
    "music_search_query": "motivational instrumental",
    "music_mood": "motivational",
    "music_bpm_preference": "medium",
    "creative_direction": "smooth flow",
    "music_volume": 0.12,
    "duck_strength": "medium",
    "music_fade_in_sec": 1.0,
    "music_fade_out_sec": 2.0,
    "music_creative_brief": "",
    "caption": {
        "hook": "You need to see this.",
        "body": "Watch till the end.",
        "cta": "Follow for more.",
        "hashtags": ["#reels", "#viral", "#content"],
    },
    "director_notes": "Clean edit.",
    "estimated_reel_duration_sec": 14,
}


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess mock — handles ffprobe and ffmpeg
# ─────────────────────────────────────────────────────────────────────────────

def _mock_subprocess_run(*args, **kwargs):
    """Mock subprocess.run for ffprobe and ffmpeg."""
    cmd = args[0] if args else []
    cmd_str = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)

    # ffprobe — return duration or video info
    if "ffprobe" in cmd_str:
        result = MagicMock()
        result.returncode = 0
        if "format=duration" in cmd_str:
            result.stdout = "15.0"
            result.stderr = ""
        elif "show_streams" in cmd_str:
            result.stdout = json.dumps({
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080},
                    {"codec_type": "audio"},
                ],
                "format": {},
            })
            result.stderr = ""
        return result

    # ffmpeg — create output file
    if "ffmpeg" in cmd_str:
        for i, arg in enumerate(cmd):
            if arg == "-y" and i + 1 < len(cmd):
                out_path = Path(cmd[i + 1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if out_path.suffix.lower() in (".jpg", ".jpeg"):
                    out_path.write_bytes(MINIMAL_JPEG_BYTES)
                else:
                    out_path.write_bytes(b"fake_audio_or_video_content")
                break
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    # Fallback: real subprocess
    return subprocess.run(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Groq mock — Whisper + Chat Completions
# ─────────────────────────────────────────────────────────────────────────────

def _make_whisper_response():
    """Mock Groq Whisper transcription response."""
    resp = MagicMock()
    resp.text = SAMPLE_TRANSCRIPT["full_text"]
    resp.words = [
        {"word": w["word"], "start": w["start"], "end": w["end"]}
        for w in SAMPLE_TRANSCRIPT["words"]
    ]
    resp.segments = [
        {"text": s["text"], "start": s["start"], "end": s["end"]}
        for s in SAMPLE_TRANSCRIPT["segments"]
    ]
    resp.language = "en"
    return resp


def _make_chat_response(content: str):
    """Mock Groq chat completion response."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


def _create_groq_mock(call_responses: dict):
    """
    Create a Groq client mock that returns different responses based on call type.
    call_responses: {
        "transcribe": response or None (uses default),
        "chat_transcriber": content,
        "chat_video_analyst": content,
        "chat_holistic": content,
        "chat_brain": content,
        "chat_music_refine": content,
        "chat_music_pick": content,
    }
    """
    call_count = {"transcribe": 0, "chat": 0}

    def audio_create(*args, **kwargs):
        call_count["transcribe"] += 1
        r = call_responses.get("transcribe") or _make_whisper_response()
        return r

    def chat_create(*args, **kwargs):
        call_count["chat"] += 1
        messages = kwargs.get("messages", [])
        msg_str = str(messages)
        content = None
        # Determine which agent based on message content (order matters: more specific first)
        if "search_query" in msg_str and "Respond ONLY with JSON" in msg_str:
            content = call_responses.get("chat_music_refine") or '{"search_query": "motivational instrumental", "reason": "test"}'
        elif "chosen_index" in msg_str and "Options:" in msg_str:
            content = call_responses.get("chat_music_pick") or '{"chosen_index": 0, "reason": "best match"}'
        elif "needs_subtitles" in msg_str and "subtitle_style" in msg_str:
            content = call_responses.get("chat_subtitle_verifier") or json.dumps({
                "transcription_verified": True,
                "transcription_notes": "Clear speech",
                "needs_subtitles": True,
                "needs_subtitles_reason": "Talking head content benefits from subs",
                "subtitle_style": "hormozi",
                "subtitle_style_reason": "High contrast for motivational content",
            })
        elif "narrative_order" in msg_str and "trim_start_sec" in msg_str:
            content = call_responses.get("chat_brain") or json.dumps(SAMPLE_EDIT_PLAN)
        elif "content_type" in msg_str and "talking_head" in msg_str and "visual_quality" in msg_str:
            content = call_responses.get("chat_video_analyst") or json.dumps(SAMPLE_ANALYSIS)
        elif "overall_impression" in msg_str and "best_clip_for_hook" in msg_str:
            content = call_responses.get("chat_holistic") or json.dumps(SAMPLE_HOLISTIC_REVIEW)
        else:
            content = call_responses.get("chat_default") or json.dumps(SAMPLE_HOLISTIC_REVIEW)
        return _make_chat_response(content)

    client = MagicMock()
    client.audio.transcriptions.create = MagicMock(side_effect=audio_create)
    client.chat.completions.create = MagicMock(side_effect=chat_create)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# httpx mock — Internet Archive
# ─────────────────────────────────────────────────────────────────────────────

def _make_ia_search_response():
    return {
        "response": {
            "docs": [
                {
                    "identifier": "test-audio-item-001",
                    "title": "Motivational Background Music",
                    "subject": "instrumental, motivational",
                    "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
                },
            ],
        },
    }


def _make_ia_metadata_response():
    return {
        "files": [
            {
                "name": "track01.mp3",
                "format": "MP3",
                "size": 3_000_000,
            },
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_key_manager():
    """Patch key_manager in all agent modules (patch where used, not where defined)."""
    with (
        patch("agents.transcriber.has_keys", return_value=True),
        patch("agents.transcriber.next_key", return_value="test-groq-key-12345"),
        patch("agents.video_analyst.has_keys", return_value=True),
        patch("agents.video_analyst.next_key", return_value="test-groq-key-12345"),
        patch("agents.holistic_reviewer.has_keys", return_value=True),
        patch("agents.holistic_reviewer.next_key", return_value="test-groq-key-12345"),
        patch("agents.brain.has_keys", return_value=True),
        patch("agents.brain.next_key", return_value="test-groq-key-12345"),
        patch("agents.music_supervisor.has_keys", return_value=True),
        patch("agents.music_supervisor.next_key", return_value="test-groq-key-12345"),
        patch("agents.subtitle_verifier.has_keys", return_value=True),
        patch("agents.subtitle_verifier.next_key", return_value="test-groq-key-12345"),
    ):
        yield


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run for ffmpeg/ffprobe."""
    with patch("subprocess.run", side_effect=_mock_subprocess_run):
        yield


@pytest.fixture
def mock_groq():
    """Patch Groq client in all agent modules."""
    client = _create_groq_mock({})
    with (
        patch("agents.transcriber.Groq", return_value=client),
        patch("agents.video_analyst.Groq", return_value=client),
        patch("agents.holistic_reviewer.Groq", return_value=client),
        patch("agents.brain.Groq", return_value=client),
        patch("agents.music_supervisor.Groq", return_value=client),
        patch("agents.subtitle_verifier.Groq", return_value=client),
    ):
        yield client


@pytest.fixture
def mock_httpx():
    """Patch httpx for Internet Archive API."""
    def _get(url, *args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.status_code = 200
        if "advancedsearch" in url:
            resp.json.return_value = _make_ia_search_response()
        elif "metadata" in url:
            resp.json.return_value = _make_ia_metadata_response()
        else:
            resp.content = b"fake_mp3_content"
        return resp

    with patch("httpx.Client") as mock_client:
        instance = MagicMock()
        instance.get = MagicMock(side_effect=_get)
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=None)
        mock_client.return_value = instance
        yield mock_client


@pytest.fixture
def sample_video_path(tmp_path):
    """Create a minimal video file that exists (for path checks)."""
    video = tmp_path / "test_clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00mp42")
    return video


@pytest.fixture
def sample_transcripts():
    """Sample transcript data for downstream agents."""
    t = SAMPLE_TRANSCRIPT.copy()
    t["clip_index"] = 0
    return [t]


@pytest.fixture
def sample_analyses():
    """Sample analysis data for downstream agents."""
    a = SAMPLE_ANALYSIS.copy()
    a["clip_index"] = 0
    return [a]


@pytest.fixture
def sample_edit_plan():
    """Sample edit plan from Brain."""
    return json.loads(json.dumps(SAMPLE_EDIT_PLAN))


@pytest.fixture
def all_mocks(mock_key_manager, mock_subprocess, mock_groq, mock_httpx):
    """Apply all mocks for full pipeline testing."""
    yield {
        "key_manager": mock_key_manager,
        "subprocess": mock_subprocess,
        "groq": mock_groq,
        "httpx": mock_httpx,
    }

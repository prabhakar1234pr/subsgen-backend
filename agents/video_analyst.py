"""
agents/video_analyst.py

Agent 2 — VideoAnalyst
Uses Llama 4 Scout (vision) via Groq to analyze sampled frames from each clip.
Now receives transcript context to give the VLM better grounding.
"""

import base64
import json
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)

VLM_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

ANALYSIS_PROMPT = """You are a professional video editor analyzing a single raw clip for an Instagram Reel.

You are shown {n_frames} frames sampled evenly through the clip.
Transcript of what is being said: "{transcript_preview}"

Analyze ONLY the visual content and respond with a JSON object. No markdown, no explanation.

{{
  "content_type": "talking_head | product_demo | lifestyle | tutorial | broll | other",
  "subject_description": "who/what is visible",
  "setting": "indoor_plain | indoor_busy | outdoor | studio | screen_recording",
  "speaker_energy": "low | medium | high",
  "speaker_confidence": "low | medium | high",
  "lighting_quality": "poor | decent | good | professional",
  "framing": "close_up | medium | wide | mixed",
  "visual_quality": "poor | decent | good | excellent",
  "dominant_colors": ["color1", "color2"],
  "recommended_subtitle_style": "hormozi | minimal | neon | fire | karaoke | purple",
  "subtitle_style_reason": "one sentence",
  "visual_hook_strength": 1-10,
  "overall_visual_score": 1-10
}}"""


def _extract_frames(video_path: Path, n_frames: int = 3) -> list[str]:
    """Extract n evenly-spaced frames as base64 JPEGs."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True
    )
    duration = float(result.stdout.strip())
    frames_b64 = []
    tmp_dir = Path(tempfile.gettempdir())

    for i in range(n_frames):
        t = duration * (0.1 + 0.8 * i / max(n_frames - 1, 1))
        frame_path = tmp_dir / f"{uuid.uuid4()}.jpg"
        try:
            subprocess.run([
                "ffmpeg", "-ss", f"{t:.2f}", "-i", str(video_path),
                "-vframes", "1", "-vf", "scale=480:-1", "-q:v", "4",
                "-y", str(frame_path)
            ], check=True, capture_output=True)
            with open(frame_path, "rb") as f:
                frames_b64.append(base64.b64encode(f.read()).decode("utf-8"))
        except Exception as e:
            logger.warning(f"Frame extraction failed at t={t:.2f}s: {e}")
        finally:
            if frame_path.exists():
                frame_path.unlink()

    return frames_b64


def analyze_clip(video_path: Path, transcript: dict, clip_index: int = 0) -> dict:
    """
    Analyze a single clip visually.
    Now accepts transcript dict from Transcriber agent for richer context.
    """
    if not has_keys():
        return _default_analysis(clip_index, video_path.name)

    frames = _extract_frames(video_path, n_frames=3)
    if not frames:
        return _default_analysis(clip_index, video_path.name)

    # Give VLM a short transcript preview for context
    transcript_preview = transcript.get("full_text", "")[:200] or "no speech detected"

    content = []
    for frame_b64 in frames:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}", "detail": "low"}
        })
    content.append({
        "type": "text",
        "text": ANALYSIS_PROMPT.format(
            n_frames=len(frames),
            transcript_preview=transcript_preview
        )
    })

    try:
        logger.info(f"[VLM] Clip {clip_index+1}: Analyzing {len(frames)} frames | transcript={transcript_preview[:60]}...")
        client = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model=VLM_MODEL,
            messages=[{"role": "user", "content": content}],
            max_tokens=500,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(raw)
        analysis["clip_index"] = clip_index
        analysis["clip_name"]  = video_path.name
        logger.info(f"[VLM] Clip {clip_index+1}: quality={analysis.get('visual_quality')}, hook={analysis.get('visual_hook_strength')}/10")
        return analysis
    except Exception as e:
        logger.error(f"[VLM] Clip {clip_index+1} failed: {e}")
        return _default_analysis(clip_index, video_path.name)


def _default_analysis(clip_index: int, clip_name: str = "") -> dict:
    return {
        "clip_index": clip_index, "clip_name": clip_name,
        "content_type": "talking_head",
        "subject_description": "person speaking to camera",
        "setting": "indoor_plain",
        "speaker_energy": "medium", "speaker_confidence": "medium",
        "lighting_quality": "decent", "framing": "medium",
        "visual_quality": "decent",
        "dominant_colors": ["neutral"],
        "recommended_subtitle_style": "hormozi",
        "subtitle_style_reason": "Default high-contrast style",
        "visual_hook_strength": 5, "overall_visual_score": 5,
    }

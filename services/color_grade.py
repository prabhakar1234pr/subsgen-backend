"""
services/color_grade.py

Apply preset-based color grading via FFmpeg eq/curves filters.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# FFmpeg eq filter: brightness (-1..1), contrast (default 1), saturation (default 1)
PRESETS = {
    "warm": "eq=brightness=0.03:contrast=1.05:saturation=1.15:gamma=1.05",
    "cool": "eq=brightness=0.02:contrast=1.05:saturation=0.9:gamma=0.98",
    "cinematic": "eq=contrast=1.15:saturation=0.85:gamma=1.02",
    "vibrant": "eq=contrast=1.08:saturation=1.25",
    "muted": "eq=saturation=0.7:contrast=0.95",
    "high_contrast": "eq=contrast=1.2:saturation=1.05",
    "neutral": "eq=contrast=1.02:saturation=1.02",
}


def apply_color_grade(video_path: Path, output_path: Path, preset: str = "neutral") -> Path:
    """
    Apply color grading preset to video via FFmpeg eq filter.
    """
    vf = PRESETS.get(preset.lower(), PRESETS["neutral"])

    logger.info(f"[COLOR] apply_color_grade | preset={preset} | {video_path.name} -> {output_path.name}")
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y", str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.warning(f"[COLOR] Preset failed, copying without grade: {e}")
        subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-c", "copy", "-y", str(output_path)],
            check=True, capture_output=True
        )
    return output_path

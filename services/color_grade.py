"""
services/color_grade.py

Apply preset-based color grading via FFmpeg eq/curves filters.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# FFmpeg eq filter: brightness (-1..1), contrast (default 1), saturation (default 1)
# Presets are noticeable but not overdone
PRESETS = {
    "warm": "eq=brightness=0.04:contrast=1.08:saturation=1.2:gamma=1.08",
    "cool": "eq=brightness=0.02:contrast=1.08:saturation=0.88:gamma=0.95",
    "cinematic": "eq=contrast=1.18:saturation=0.82:gamma=1.05",
    "vibrant": "eq=contrast=1.1:saturation=1.3",
    "muted": "eq=saturation=0.65:contrast=0.92",
    "high_contrast": "eq=contrast=1.25:saturation=1.08",
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

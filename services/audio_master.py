"""
services/audio_master.py

Mix music under video with ducking — lower music when speech is present.
Uses word timestamps to build a volume envelope.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_speech_windows(
    words: list[dict],
    padding: float = 0.15,
) -> list[tuple[float, float]]:
    """Build (start, end) windows for speech from word timestamps. Merge overlapping."""
    if not words:
        return []
    windows = []
    for w in words:
        s, e = w["start"], w["end"]
        windows.append((max(0, s - padding), e + padding))
    # Sort and merge overlapping
    windows.sort(key=lambda x: x[0])
    merged = [windows[0]]
    for s, e in windows[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _build_volume_expr(
    windows: list[tuple[float, float]],
    duck_vol: float,
    normal_vol: float,
) -> str:
    """Build FFmpeg volume expression: duck when t in any window."""
    if not windows:
        return str(normal_vol)
    parts = [f"between(t,{s:.2f},{e:.2f})" for s, e in windows]
    expr = "+".join(parts)
    return f"if({expr},{duck_vol},{normal_vol})"


def mix_with_ducking(
    video_path: Path,
    music_path: Path,
    word_timestamps: list[dict],
    output_path: Path,
    music_volume: float = 0.12,
    duck_volume: float = 0.04,
    duck_strength: str = "medium",
    fade_in: float = 1.0,
    fade_out: float = 2.0,
) -> Path:
    """
    Mix music under video, ducking when speech is present.
    word_timestamps: [{"start": float, "end": float}, ...]
    duck_strength: light (0.06), medium (0.04), heavy (0.02)
    """
    duck_vol = {"light": 0.06, "medium": 0.04, "heavy": 0.02}.get(
        duck_strength.lower(), 0.04
    )

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True)
    dur = float(r.stdout.strip())
    fs = max(0.0, dur - fade_out)

    windows = _build_speech_windows(word_timestamps)
    vol_expr = _build_volume_expr(windows, duck_vol, music_volume)

    logger.info(f"[AUDIO] mix_with_ducking | {len(windows)} speech windows | duck={duck_strength}")

    # [1:a] = music: loop, trim, volume envelope (duck when speech), fades
    # [0:a] = video speech
    fc = (
        f"[1:a]aloop=loop=-1:size=2e+09,atrim=duration={dur},"
        f"volume=volume='{vol_expr}',"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fs:.3f}:d={fade_out}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    subprocess.run([
        "ffmpeg", "-i", str(video_path), "-i", str(music_path),
        "-filter_complex", fc,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", "-y", str(output_path),
    ], check=True, capture_output=True)

    logger.info("[AUDIO] mix_with_ducking done")
    return output_path

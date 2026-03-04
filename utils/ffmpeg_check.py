"""Check if FFmpeg/ffprobe are available. Required for video processing."""

import logging
import shutil
import sys

logger = logging.getLogger(__name__)


def _find_exe(name: str) -> str | None:
    """Find executable in PATH. On Windows, also try name.exe."""
    exe = shutil.which(name)
    if exe:
        return exe
    if sys.platform == "win32":
        exe = shutil.which(f"{name}.exe")
    return exe


def check_ffmpeg_available() -> tuple[bool, str]:
    """
    Check if ffmpeg and ffprobe are in PATH.
    Returns (ok, message).
    """
    ffmpeg = _find_exe("ffmpeg")
    ffprobe = _find_exe("ffprobe")
    if not ffmpeg:
        return False, "ffmpeg not found in PATH. Install from https://ffmpeg.org/download.html and add to PATH."
    if not ffprobe:
        return False, "ffprobe not found in PATH. It comes with FFmpeg - ensure the FFmpeg bin folder is in PATH."
    logger.info(f"[FFMPEG] Found: ffmpeg={ffmpeg}, ffprobe={ffprobe}")
    return True, "ok"

"""
music_selector.py

Picks a royalty-free background track from backend/assets/music/
and mixes it under the speech at low volume with fade-in/out.

Track filenames: <mood>_<anything>.mp3   e.g. motivational_rise.mp3
"""

import subprocess, logging, random
from pathlib import Path

logger = logging.getLogger(__name__)

MUSIC_DIR = Path(__file__).parent.parent / "assets" / "music"

AVAILABLE_MOODS = [
    {"id": "motivational", "label": "Motivational", "emoji": "🔥", "description": "Hustle & business energy"},
    {"id": "chill",        "label": "Chill / Lo-fi", "emoji": "😌", "description": "Relaxed lifestyle vibes"},
    {"id": "energy",       "label": "High Energy",   "emoji": "⚡", "description": "Hype & fast-paced content"},
    {"id": "uplifting",    "label": "Uplifting",      "emoji": "✨", "description": "Feel-good & inspirational"},
    {"id": "cinematic",    "label": "Cinematic",      "emoji": "🎬", "description": "Dramatic storytelling"},
]

_FALLBACK_ORDER = ["motivational", "chill", "energy", "uplifting", "cinematic"]
_MOOD_CACHE: dict = {}


def _load_tracks() -> None:
    global _MOOD_CACHE
    _MOOD_CACHE = {}
    if not MUSIC_DIR.exists():
        logger.warning(f"Music dir missing: {MUSIC_DIR}")
        return
    for f in MUSIC_DIR.glob("*.mp3"):
        mood = f.stem.split("_")[0].lower()
        _MOOD_CACHE.setdefault(mood, []).append(f)
    logger.info(f"Loaded tracks: { {k: len(v) for k,v in _MOOD_CACHE.items()} }")


def get_track(mood: str) -> Path | None:
    if not _MOOD_CACHE:
        _load_tracks()
    mood = mood.lower()
    if mood in _MOOD_CACHE:
        return random.choice(_MOOD_CACHE[mood])
    for fb in _FALLBACK_ORDER:
        if fb in _MOOD_CACHE:
            logger.info(f"No tracks for '{mood}', using fallback '{fb}'")
            return random.choice(_MOOD_CACHE[fb])
    return None


def mix_music(video_path: Path, output_path: Path,
              mood: str = "motivational",
              music_vol: float = 0.10,
              fade_in: float = 1.0,
              fade_out: float = 2.0) -> Path:
    """
    Mix a looping background track under speech at low volume.
    Copies video stream unchanged; re-encodes audio only.
    Falls back to copy if no tracks available.
    """
    track = get_track(mood)
    if track is None:
        logger.warning("No music tracks - skipping music mix")
        subprocess.run(["ffmpeg","-i",str(video_path),"-c","copy","-y",str(output_path)],
                       check=True, capture_output=True)
        return output_path

    duration = float(subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(video_path)],
        capture_output=True, text=True, check=True).stdout.strip())

    fade_start = max(0.0, duration - fade_out)
    logger.info(f"Mixing '{track.name}' at vol={music_vol} over {duration:.1f}s")

    fc = (
        f"[1:a]aloop=loop=-1:size=2e+09,"
        f"atrim=duration={duration},"
        f"volume={music_vol},"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_start:.3f}:d={fade_out}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )
    subprocess.run([
        "ffmpeg","-i",str(video_path),"-i",str(track),
        "-filter_complex",fc,
        "-map","0:v","-map","[aout]",
        "-c:v","copy","-c:a","aac","-b:a","192k",
        "-shortest","-movflags","+faststart","-y",str(output_path),
    ], check=True, capture_output=True)
    logger.info("Music mixed OK")
    return output_path

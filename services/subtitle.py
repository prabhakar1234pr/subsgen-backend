import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format (H:MM:SS.cc)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


# Subtitle style definitions
# Colors in ASS format: &HAABBGGRR (Alpha, Blue, Green, Red)
SUBTITLE_STYLES = {
    "hormozi": {
        "name": "Hormozi",
        "primary": "&H00FFFFFF",      # White
        "highlight": "&H0000FFFF",    # Yellow (BGR)
        "outline": "&H00000000",      # Black
        "back": "&H80000000",         # Semi-transparent black
        "fontsize": 80,
    },
    "minimal": {
        "name": "Minimal",
        "primary": "&H00FFFFFF",      # White
        "highlight": "&H00FFFFFF",    # White (no highlight)
        "outline": "&H00000000",      # Black
        "back": "&H00000000",         # Transparent
        "fontsize": 70,
    },
    "neon": {
        "name": "Neon Glow",
        "primary": "&H00FFFF00",      # Cyan (BGR)
        "highlight": "&H00FF00FF",    # Magenta (BGR)
        "outline": "&H00FF00FF",      # Magenta outline
        "back": "&H80000000",         # Semi-transparent
        "fontsize": 80,
    },
    "fire": {
        "name": "Fire",
        "primary": "&H00FFFFFF",      # White
        "highlight": "&H000066FF",    # Orange (BGR)
        "outline": "&H00000000",      # Black
        "back": "&H80000000",         # Semi-transparent
        "fontsize": 80,
    },
    "karaoke": {
        "name": "Karaoke",
        "primary": "&H00FFFFFF",      # White
        "highlight": "&H0000FF00",    # Green (BGR)
        "outline": "&H00000000",      # Black
        "back": "&H80000000",         # Semi-transparent
        "fontsize": 80,
    },
    "purple": {
        "name": "Purple Vibes",
        "primary": "&H00FFFFFF",      # White
        "highlight": "&H00F755A8",    # Purple (BGR)
        "outline": "&H00000000",      # Black
        "back": "&H80000000",         # Semi-transparent
        "fontsize": 80,
    },
}


def generate_ass_subtitles(words: list[dict], output_path: Path, style: str = "hormozi") -> Path:
    """
    Generate ASS subtitle file with word-by-word highlighting.
    
    Supports multiple styles for different looks.
    """
    logger.info(f"[SUBTITLE] generate_ass_subtitles | words={len(words)} | style={style} | out={output_path.name}")
    # Get style config or default to hormozi
    style_config = SUBTITLE_STYLES.get(style, SUBTITLE_STYLES["hormozi"])
    
    primary_color = style_config["primary"]
    highlight_color = style_config["highlight"]
    outline_color = style_config["outline"]
    back_color = style_config["back"]
    fontsize = style_config["fontsize"]
    
    # ASS header with styling
    ass_header = f"""[Script Info]
Title: Instagram Style Subtitles
ScriptType: v4.00+
PlayDepth: 0
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,{fontsize},{primary_color},&H000000FF,{outline_color},{back_color},1,0,0,0,100,100,0,0,3,4,0,2,40,40,200,1
Style: Highlight,Impact,{fontsize},{highlight_color},&H000000FF,{outline_color},{back_color},1,0,0,0,100,100,0,0,3,4,0,2,40,40,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    
    # Group words into chunks (3-4 words per display)
    chunk_size = 3
    word_chunks = []
    
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        word_chunks.append(chunk)

    # Convert highlight color for inline use (remove &H00 prefix)
    inline_highlight = highlight_color.replace("&H00", "&H")
    inline_primary = primary_color.replace("&H00", "&H")

    for chunk in word_chunks:
        if not chunk:
            continue
            
        # For each word in the chunk, create highlighted version
        for i, current_word in enumerate(chunk):
            word_start = current_word["start"]
            word_end = current_word["end"]
            
            # Build the text with current word highlighted
            text_parts = []
            for j, w in enumerate(chunk):
                if j == i:
                    # Highlight current word
                    text_parts.append(r"{\c" + inline_highlight + r"}" + w["word"].upper() + r"{\c" + inline_primary + r"}")
                else:
                    text_parts.append(w["word"].upper())
            
            text = " ".join(text_parts)
            
            start_time = seconds_to_ass_time(word_start)
            end_time = seconds_to_ass_time(word_end)
            
            event = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            events.append(event)

    # Write ASS file
    ass_content = ass_header + "\n".join(events)
    output_path.write_text(ass_content, encoding="utf-8")
    logger.debug(f"[SUBTITLE] Wrote {len(events)} events to {output_path.name}")
    return output_path


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path
) -> Path:
    """
    Burn ASS subtitles onto video using FFmpeg.
    Optimized for maximum speed on CPU.
    
    Returns path to output video.
    """
    logger.info(f"[SUBTITLE] burn_subtitles | video={video_path.name} | subs={subtitle_path.name} | out={output_path.name}")
    # FFmpeg command - maximum speed optimizations
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"ass={str(subtitle_path)}",
        "-c:v", "libx264",
        "-preset", "ultrafast",  # Fastest encoding
        "-tune", "fastdecode",   # Optimize for fast decode
        "-crf", "28",            # Slightly lower quality = faster
        "-threads", "0",         # Use all CPU threads
        "-c:a", "aac",
        "-b:a", "128k",          # Fixed audio bitrate - faster
        "-movflags", "+faststart",
        "-y",
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    
    return output_path


def copy_video(video_path: Path, output_path: Path) -> Path:
    """Copy video without re-encoding (for clips with no speech)."""
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-c", "copy",
        "-y",
        str(output_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    """Extract audio from video for transcription. Optimized for speed."""
    logger.debug(f"[SUBTITLE] extract_audio | video={video_path.name} -> {audio_path.name}")
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",              # No video
        "-acodec", "pcm_s16le",
        "-ar", "16000",     # Whisper expects 16kHz
        "-ac", "1",         # Mono
        "-threads", "0",    # Use all CPU threads
        "-y",
        str(audio_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    
    return audio_path

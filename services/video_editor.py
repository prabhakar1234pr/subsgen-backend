"""
services/video_editor.py

FFmpeg editing — now uses Brain's exact trim points instead of silence detection.
  1. Precise trim     (Brain-specified start_sec / end_sec)
  2. Reframe to 9:16  (1080x1920)
  3. Crossfade concat
"""

import subprocess, json, logging, os, tempfile, uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def _tmp(ext=".mp4") -> Path:
    return Path(tempfile.gettempdir()) / f"{uuid.uuid4()}{ext}"


def get_video_info(p: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", str(p)],
        capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def get_duration(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def precise_trim(video_path: Path, output_path: Path,
                 start_sec: float, end_sec: float) -> Path:
    """Trim clip to exact Brain-specified start/end times."""
    duration = end_sec - start_sec
    if duration < 0.5:
        logger.warning(f"Trim duration {duration:.2f}s too short — copying full clip")
        subprocess.run(["ffmpeg", "-i", str(video_path), "-c", "copy",
                        "-y", str(output_path)], check=True, capture_output=True)
        return output_path

    logger.info(f"Precise trim: {start_sec:.2f}s → {end_sec:.2f}s ({duration:.2f}s)")
    subprocess.run([
        "ffmpeg",
        "-ss", f"{start_sec:.3f}",
        "-to", f"{end_sec:.3f}",
        "-i", str(video_path),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-avoid_negative_ts", "1",
        "-y", str(output_path),
    ], check=True, capture_output=True)
    return output_path


def reframe_to_9x16(video_path: Path, output_path: Path) -> Path:
    """Scale/crop to 1080x1920."""
    info = get_video_info(video_path)
    vs   = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not vs:
        raise ValueError("No video stream found")
    w, h = int(vs["width"]), int(vs["height"])
    if w > h:
        cw = int(h * 9 / 16)
        cx = (w - cw) // 2
        vf = f"crop={cw}:{h}:{cx}:0,scale=1080:1920:flags=lanczos"
    else:
        vf = "scale=1080:-2:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
    subprocess.run([
        "ffmpeg", "-i", str(video_path), "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-y", str(output_path),
    ], check=True, capture_output=True)
    logger.info(f"Reframed {w}x{h} → 1080x1920")
    return output_path


def _normalise(p: Path, out: Path) -> Path:
    """Ensure consistent fps/resolution/audio for xfade."""
    subprocess.run([
        "ffmpeg", "-i", str(p),
        "-vf", "fps=30,scale=1080:1920:flags=lanczos",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-y", str(out),
    ], check=True, capture_output=True)
    return out


def _simple_concat(paths: list, out: Path) -> Path:
    lst = _tmp(".txt")
    lst.write_text("\n".join(f"file '{p}'" for p in paths))
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-y", str(out),
    ], check=True, capture_output=True)
    lst.unlink(missing_ok=True)
    return out


def concat_with_crossfade(clip_paths: list, output_path: Path,
                           xfade_sec: float = 0.35) -> Path:
    if len(clip_paths) == 1:
        subprocess.run(["ffmpeg", "-i", str(clip_paths[0]), "-c", "copy",
                        "-y", str(output_path)], check=True, capture_output=True)
        return output_path

    tmp_files = []
    try:
        normed = []
        for p in clip_paths:
            t = _tmp(); tmp_files.append(t)
            normed.append(_normalise(p, t))

        durations = [get_duration(p) for p in normed]
        n = len(normed)
        parts  = []
        prev_v, prev_a = "[0:v]", "[0:a]"
        offset = durations[0] - xfade_sec

        for i in range(1, n):
            ov = "[vout]" if i == n-1 else f"[v{i}]"
            oa = "[aout]" if i == n-1 else f"[a{i}]"
            parts.append(f"{prev_v}[{i}:v]xfade=transition=fade:duration={xfade_sec}:offset={offset:.3f}{ov}")
            parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_sec}{oa}")
            prev_v, prev_a = ov, oa
            if i < n-1:
                offset += durations[i] - xfade_sec

        cmd = ["ffmpeg"]
        for p in normed: cmd += ["-i", str(p)]
        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-y", str(output_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.warning("xfade failed — falling back to simple concat")
            _simple_concat(normed, output_path)
    finally:
        for t in tmp_files:
            if t.exists(): os.remove(t)

    return output_path


def produce_reel(
    ordered_clips: list,   # list of (Path, trim_start_sec, trim_end_sec)
    output_path: Path,
    xfade_sec: float = 0.35,
) -> Path:
    """
    Execute the Brain's edit plan:
      1. Precisely trim each clip
      2. Reframe each to 9:16
      3. Concat with crossfade
    """
    edited, tmp_files = [], []
    try:
        for i, (clip_path, trim_start, trim_end) in enumerate(ordered_clips):
            logger.info(f"Processing clip {i+1}/{len(ordered_clips)}: {clip_path.name} [{trim_start:.2f}→{trim_end:.2f}s]")

            # Step A: precise trim
            trimmed = _tmp(); tmp_files.append(trimmed)
            precise_trim(clip_path, trimmed, trim_start, trim_end)

            # Step B: reframe
            framed = _tmp(); tmp_files.append(framed)
            reframe_to_9x16(trimmed, framed)
            edited.append(framed)

        logger.info(f"Concatenating {len(edited)} clips with {xfade_sec}s crossfade...")
        concat_with_crossfade(edited, output_path, xfade_sec=xfade_sec)

    finally:
        for t in tmp_files:
            if t.exists(): os.remove(t)

    return output_path

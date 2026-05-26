from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _concat_with_ffmpeg(video_paths: list[str], output_path: str) -> None:
    list_path = Path(output_path).with_suffix(".concat.txt")
    lines = []
    for path in video_paths:
        safe_path = str(Path(path).resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def render_trip_video(
    media_paths: list[str],
    story_plan: dict[str, Any],
    output_path: str,
    metadata_path: str | None = None,
) -> str:
    """Create a holiday recap assembly from uploaded videos.

    If ffmpeg is available, all uploaded videos are concatenated and re-encoded.
    If ffmpeg is unavailable, the first uploaded video is copied as the render
    output so the session still produces a usable artifact and voiceover plan.
    """

    video_paths = [path for path in media_paths if Path(path).suffix.lower() in VIDEO_SUFFIXES and Path(path).exists()]
    if not video_paths:
        raise ValueError("Upload at least one video clip to render a recap video.")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if _ffmpeg_available() and len(video_paths) > 1:
        _concat_with_ffmpeg(video_paths, output_path)
    elif _ffmpeg_available() and len(video_paths) == 1:
        shutil.copyfile(video_paths[0], output_path)
    else:
        shutil.copyfile(video_paths[0], output_path)

    if metadata_path:
        Path(metadata_path).write_text(json.dumps(story_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    return output_path

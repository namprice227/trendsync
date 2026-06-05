from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def media_binary(name: str, env_name: str) -> str | None:
    configured = os.environ.get(env_name, "").strip()
    if configured:
        return configured
    found = shutil.which(name)
    if found:
        return found
    sibling = Path(sys.executable).resolve().parent / name
    if sibling.exists():
        return str(sibling)
    return None


def ffmpeg_bin() -> str | None:
    return media_binary("ffmpeg", "TRIPSTORY_FFMPEG_BIN")


def ffprobe_bin() -> str | None:
    return media_binary("ffprobe", "TRIPSTORY_FFPROBE_BIN")

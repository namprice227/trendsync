from __future__ import annotations

import base64
import json
import math
import os
import random
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests

from tripstory_logging import approximate_tokens, get_logger, log_event
from media_tools import ffmpeg_bin, ffprobe_bin


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
_vision_lock = threading.Lock()
_last_vision_request_at = 0.0
logger = get_logger("media")
FFMPEG_PROBE_TIMEOUT = int(os.environ.get("TRIPSTORY_FFMPEG_PROBE_TIMEOUT", "30"))
FFMPEG_AUDIO_TIMEOUT = int(os.environ.get("TRIPSTORY_FFMPEG_AUDIO_TIMEOUT", "45"))

VISION_PRESETS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model_env": "TRIPSTORY_GEMINI_VISION_MODEL",
        "model": "gemini-2.0-flash",
        "semantic_source": "gemini_vision",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "TRIPSTORY_OPENAI_VISION_MODEL",
        "model": "gpt-4o-mini",
        "semantic_source": "openai_vision",
    },
}


def _run_json(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=FFMPEG_PROBE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _probe(path: Path) -> dict[str, Any]:
    ffprobe = ffprobe_bin()
    if not ffprobe:
        return {
            "duration_seconds": 0.0,
            "width": 0,
            "height": 0,
            "fps": 0.0,
            "bit_rate": 0,
            "has_audio": False,
        }
    data = _run_json(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,bit_rate:stream=index,codec_type,width,height,r_frame_rate,duration",
            "-of",
            "json",
            str(path),
        ]
    )
    streams = data.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    duration = _float(data.get("format", {}).get("duration")) or _float(video.get("duration")) or 0.0
    return {
        "duration_seconds": round(duration, 2),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": round(_fps(video.get("r_frame_rate")), 2),
        "bit_rate": int(data.get("format", {}).get("bit_rate") or 0),
        "has_audio": bool(audio),
    }


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fps(value: Any) -> float:
    if not value or not isinstance(value, str):
        return 0.0
    if "/" not in value:
        return _float(value)
    numerator, denominator = value.split("/", 1)
    den = _float(denominator)
    return _float(numerator) / den if den else 0.0


def _audio_levels(path: Path) -> dict[str, Any]:
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        return {"mean_volume_db": None, "max_volume_db": None}
    command = [ffmpeg, "-nostdin", "-hide_banner", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"]
    try:
        result = subprocess.run(command, check=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=FFMPEG_AUDIO_TIMEOUT)
    except subprocess.TimeoutExpired:
        log_event(logger, 30, "audio_level_probe_timeout", clip_name=path.name, timeout_seconds=FFMPEG_AUDIO_TIMEOUT, outcome="fallback_without_audio_levels", stage="clip_analysis")
        return {"mean_volume_db": None, "max_volume_db": None}
    except OSError:
        return {"mean_volume_db": None, "max_volume_db": None}
    text = result.stderr
    return {
        "mean_volume_db": _parse_db(text, "mean_volume:"),
        "max_volume_db": _parse_db(text, "max_volume:"),
    }


def _parse_db(text: str, marker: str) -> float | None:
    for line in text.splitlines():
        if marker not in line:
            continue
        value = line.split(marker, 1)[1].strip().split(" ", 1)[0]
        parsed = _float(value)
        return round(parsed, 2)
    return None


def _sample_visuals(path: Path, duration: float) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {
            "sampled_frames": 0,
            "avg_brightness": None,
            "avg_sharpness": None,
            "avg_motion": None,
            "face_count": 0,
            "scene_count": 0,
            "scene_timestamps": [],
            "best_moment_timestamps": [],
            "landmark_candidate_timestamps": [],
            "quality_label": "unknown",
        }

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if not duration and fps and frame_count:
        duration = frame_count / fps

    max_samples = int(os.environ.get("TRIPSTORY_ANALYSIS_MAX_FRAMES", "80"))
    interval = max(1, math.floor(frame_count / max_samples)) if frame_count else max(1, math.floor(fps * 1.5))
    face_cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))

    brightness: list[float] = []
    sharpness: list[float] = []
    motion: list[float] = []
    scene_timestamps: list[float] = []
    face_count = 0
    prev_gray = None
    prev_hist = None
    scored_frames: list[tuple[float, float]] = []
    landmark_candidates: list[tuple[float, float]] = []
    frame_records: list[dict[str, Any]] = []

    index = 0
    sampled = 0
    while sampled < max_samples:
        ok, frame = capture.read()
        if not ok:
            break
        if index % interval != 0:
            index += 1
            continue
        timestamp = index / fps if fps else 0.0
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        bright = float(np.mean(gray))
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        hist = cv2.calcHist([small], [0], None, [32], [0, 256])
        cv2.normalize(hist, hist)
        motion_score = float(np.mean(cv2.absdiff(small, prev_gray))) if prev_gray is not None else 0.0
        scene_delta = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)) if prev_hist is not None else 0.0
        if scene_delta > 0.55:
            # Merge very low-value scenes (less than 1.5 seconds long)
            if not scene_timestamps or (timestamp - scene_timestamps[-1] >= 1.5):
                scene_timestamps.append(round(timestamp, 2))

        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
        face_count += len(faces)
        brightness.append(bright)
        sharpness.append(blur_score)
        motion.append(motion_score)
        quality_score = _quality_score(bright, blur_score, motion_score, len(faces))
        scored_frames.append((quality_score, timestamp))
        frame_records.append(
            {
                "timestamp": round(timestamp, 2),
                "score": quality_score,
                "brightness": round(bright, 2),
                "sharpness": round(blur_score, 2),
                "motion": round(motion_score, 2),
                "face_count": int(len(faces)),
                "scene_change": scene_delta > 0.55,
            }
        )
        if blur_score > 140 and 55 <= bright <= 205 and not len(faces):
            landmark_candidates.append((quality_score, timestamp))

        prev_gray = small
        prev_hist = hist
        sampled += 1
        index += 1

    capture.release()
    scored_frames.sort(reverse=True)
    landmark_candidates.sort(reverse=True)
    avg_brightness = _avg(brightness)
    avg_sharpness = _avg(sharpness)
    avg_motion = _avg(motion)
    return {
        "sampled_frames": sampled,
        "avg_brightness": round(avg_brightness, 2) if avg_brightness is not None else None,
        "avg_sharpness": round(avg_sharpness, 2) if avg_sharpness is not None else None,
        "avg_motion": round(avg_motion, 2) if avg_motion is not None else None,
        "face_count": int(face_count),
        "scene_count": max(1, len(scene_timestamps) + 1) if sampled else 0,
        "scene_timestamps": scene_timestamps[:20],
        "best_moment_timestamps": [round(timestamp, 2) for _, timestamp in scored_frames[:5]],
        "landmark_candidate_timestamps": [round(timestamp, 2) for _, timestamp in landmark_candidates[:5]],
        "quality_label": _quality_label(avg_brightness, avg_sharpness),
        "smart_windows": _build_smart_windows(frame_records, duration, scene_timestamps),
    }


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _quality_score(brightness: float, sharpness: float, motion: float, faces: int) -> float:
    exposure = max(0.0, 1.0 - abs(brightness - 128.0) / 128.0)
    sharp = min(sharpness / 280.0, 1.0)
    stable_motion = max(0.0, 1.0 - min(motion / 45.0, 1.0))
    return round(exposure * 0.3 + sharp * 0.35 + stable_motion * 0.15 + min(faces, 3) * 0.08, 4)


def _quality_label(brightness: float | None, sharpness: float | None) -> str:
    if brightness is None or sharpness is None:
        return "unknown"
    if sharpness < 45:
        return "soft or shaky"
    if brightness < 45:
        return "dark"
    if brightness > 220:
        return "overexposed"
    if sharpness > 160:
        return "strong"
    return "usable"


def _bounded_window_duration(duration: float, requested: float | None = None) -> float:
    base = requested if requested is not None else _float(os.environ.get("TRIPSTORY_SMART_WINDOW_SECONDS")) or 5.5
    base = max(2.0, min(8.0, float(base)))
    if duration > 0:
        base = min(base, max(1.0, duration))
    return round(base, 2)


def _records_in_range(records: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if start <= _float(record.get("timestamp")) <= end
    ]


def _nearest_records(records: list[dict[str, Any]], center: float, limit: int = 3) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: abs(_float(record.get("timestamp")) - center))[:limit]


def _window_frame_timestamps(records: list[dict[str, Any]], start: float, duration: float, center: float) -> list[float]:
    end = start + duration
    candidates = _records_in_range(records, start, end) or _nearest_records(records, center, 3)
    candidates = sorted(candidates, key=lambda record: (abs(_float(record.get("timestamp")) - center), -_float(record.get("score"))))
    timestamps = sorted({_float(record.get("timestamp")) for record in candidates[:3]})
    return [round(timestamp, 2) for timestamp in timestamps]


def _window_metric_evidence(records: list[dict[str, Any]], start: float, duration: float) -> str:
    window_records = _records_in_range(records, start, start + duration)
    if not window_records:
        return "usable travel moment selected from the OpenCV scan"
    brightness = _avg([_float(record.get("brightness")) for record in window_records])
    sharpness = _avg([_float(record.get("sharpness")) for record in window_records])
    motion = _avg([_float(record.get("motion")) for record in window_records])
    face_hits = sum(int(_float(record.get("face_count"))) for record in window_records)
    quality = _quality_label(brightness, sharpness)
    cues = []
    if quality in {"dark", "overexposed", "soft or shaky"}:
        cues.append(f"{quality} avoid window")
    elif quality == "strong":
        cues.append("sharp, well-exposed travel window")
    else:
        cues.append("usable travel window")
    if face_hits:
        cues.append("faces or people visible")
    if motion is not None and motion >= 24:
        cues.append("active motion")
    elif motion is not None and motion <= 8:
        cues.append("steady framing")
    if any(record.get("scene_change") for record in window_records):
        cues.append("near a scene change")
    return "; ".join(cues[:4])


def _candidate_score_for_timestamp(records: list[dict[str, Any]], timestamp: float, boost: float = 0.0) -> float:
    if not records:
        return round(0.25 + boost, 4)
    nearest = min(records, key=lambda record: abs(_float(record.get("timestamp")) - timestamp))
    return round(min(1.0, _float(nearest.get("score")) + boost), 4)


def _build_smart_windows(records: list[dict[str, Any]], duration: float, scene_timestamps: list[float]) -> list[dict[str, Any]]:
    if not records and duration <= 0:
        return []
    max_windows = max(1, min(20, int(os.environ.get("TRIPSTORY_SMART_MAX_WINDOWS", "8"))))
    window_duration = _bounded_window_duration(duration)
    candidates: list[tuple[float, float]] = []
    for record in records:
        candidates.append((_float(record.get("score")), _float(record.get("timestamp"))))
    for timestamp in scene_timestamps:
        candidates.append((_candidate_score_for_timestamp(records, _float(timestamp), 0.04), _float(timestamp)))
    if not candidates:
        candidates.append((0.25, 0.0))
    candidates.sort(key=lambda item: (-item[0], item[1]))

    selected: list[dict[str, Any]] = []
    seen_centers: list[float] = []
    for score, center in candidates:
        if len(selected) >= max_windows:
            break
        if any(abs(center - existing) < window_duration * 0.6 for existing in seen_centers):
            continue
        start = max(0.0, center - window_duration / 2)
        if duration > 0:
            start = min(start, max(0.0, duration - window_duration))
        frame_timestamps = _window_frame_timestamps(records, start, window_duration, center)
        selected.append(
            {
                "window_id": f"win_{len(selected) + 1:03d}",
                "start_time": round(start, 2),
                "duration": round(window_duration, 2),
                "score": round(max(0.0, min(1.0, score)), 4),
                "frame_timestamps": frame_timestamps,
                "visual_evidence": _window_metric_evidence(records, start, window_duration),
            }
        )
        seen_centers.append(center)
    return selected


def _extract_audio_sample(path: Path) -> Path | None:
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        return None
    target = Path(tempfile.gettempdir()) / f"tripstory_transcribe_{path.stem}.mp3"
    command = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-i",
        str(path),
        "-t",
        os.environ.get("TRIPSTORY_TRANSCRIBE_SECONDS", "120"),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(target),
    ]
    try:
        result = subprocess.run(command, check=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=FFMPEG_AUDIO_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return target if result.returncode == 0 and target.exists() and target.stat().st_size else None


def _transcribe(path: Path, has_audio: bool) -> str | None:
    if not has_audio or os.environ.get("TRIPSTORY_ENABLE_TRANSCRIPTION", "").lower() not in {"1", "true", "yes"}:
        return None
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    sample = _extract_audio_sample(path)
    if not sample:
        return None
    try:
        started = time.monotonic()
        with sample.open("rb") as handle:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": os.environ.get("TRIPSTORY_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")},
                files={"file": (sample.name, handle, "audio/mpeg")},
                timeout=int(os.environ.get("TRIPSTORY_TRANSCRIPTION_TIMEOUT", "90")),
            )
        response.raise_for_status()
        data = response.json()
        text = str(data.get("text") or "").strip()
        log_event(
            logger,
            20,
            "transcription_complete",
            provider="openai",
            model=os.environ.get("TRIPSTORY_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
            clip_name=path.name,
            status_code=response.status_code,
            output_chars=len(text),
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="success" if text else "empty",
            stage="clip_analysis",
        )
        return text or None
    except Exception as exc:
        log_event(
            logger,
            30,
            "transcription_unavailable",
            provider="openai",
            model=os.environ.get("TRIPSTORY_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
            clip_name=path.name,
            exception_type=type(exc).__name__,
            outcome="fallback_without_transcript",
            stage="clip_analysis",
        )
        logger.debug("Transcription exception", exc_info=True)
        return None
    finally:
        try:
            sample.unlink()
        except OSError:
            pass


def _context_landmark_names(context: dict[str, Any] | None) -> list[str]:
    if not context:
        return []
    raw = " ".join(
        str(context.get(key) or "")
        for key in ("destination", "places_visited", "highlights", "notes")
    )
    parts = [part.strip(" .;:-") for chunk in raw.splitlines() for part in chunk.split(",")]
    return [part for part in parts if 2 <= len(part) <= 80][:12]


def _named_landmarks(analysis: dict[str, Any], context: dict[str, Any] | None) -> list[dict[str, Any]]:
    names = _context_landmark_names(context)
    timestamps = analysis.get("landmark_candidate_timestamps") or analysis.get("best_moment_timestamps") or [0]
    if not names:
        names = ["scenic exterior", "memorable place"]
    landmarks = []
    for index, timestamp in enumerate(timestamps[: min(5, len(names))]):
        landmarks.append(
            {
                "name": names[index % len(names)],
                "timestamp": timestamp,
                "confidence": 0.44 if context else 0.25,
                "source": "trip context + visual scenic candidate" if context else "visual scenic candidate",
            }
        )
    return landmarks


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _vision_provider_config() -> dict[str, str] | None:
    provider = os.environ.get("TRIPSTORY_VISION_PROVIDER", "").strip().lower()
    if not provider:
        if os.environ.get("GEMINI_API_KEY"):
            provider = "gemini"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
    preset = VISION_PRESETS.get(provider)
    if not preset:
        return None
    api_key = os.environ.get(preset["api_key_env"])
    if not api_key:
        return None
    provider_model = os.environ.get(preset["model_env"])
    generic_model = os.environ.get("TRIPSTORY_VISION_MODEL")
    model = provider_model or generic_model or preset["model"]
    if not provider_model and provider == "gemini" and model.startswith(("gpt-", "o")):
        model = preset["model"]
    if not provider_model and provider == "openai" and model.startswith("gemini-"):
        model = preset["model"]
    return {
        "provider": provider,
        "base_url": os.environ.get("TRIPSTORY_VISION_URL", preset["base_url"]).rstrip("/"),
        "api_key": api_key,
        "model": model,
        "semantic_source": preset["semantic_source"],
    }


def vision_semantics_source() -> str | None:
    if not _env_enabled("TRIPSTORY_ENABLE_VISION_ANALYSIS", bool(_vision_provider_config())):
        return None
    config = _vision_provider_config()
    return config["semantic_source"] if config else None


def _semantic_timestamps(analysis: dict[str, Any]) -> list[float]:
    candidates = []
    for key in ("best_moment_timestamps", "landmark_candidate_timestamps", "scene_timestamps"):
        for value in analysis.get(key) or []:
            try:
                timestamp = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
            if timestamp not in candidates:
                candidates.append(timestamp)
    if not candidates:
        duration = _float(analysis.get("duration_seconds"))
        candidates = [0.0, duration / 2] if duration > 4 else [0.0]
    return candidates[: max(1, int(os.environ.get("TRIPSTORY_VISION_MAX_FRAMES", "3")))]


def _frame_data_urls(path: Path, timestamps: list[float]) -> list[dict[str, Any]]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return []
    frames = []
    try:
        for timestamp in timestamps:
            capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamp) * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            height, width = frame.shape[:2]
            max_width = int(os.environ.get("TRIPSTORY_VISION_FRAME_WIDTH", "640"))
            if width > max_width:
                scale = max_width / width
                frame = cv2.resize(frame, (max_width, int(height * scale)))
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
            if not ok:
                continue
            data = base64.b64encode(encoded.tobytes()).decode("ascii")
            frames.append({"timestamp": round(timestamp, 2), "url": f"data:image/jpeg;base64,{data}"})
    finally:
        capture.release()
    return frames


def _window_frame_data_urls(path: Path, windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return []
    frames: list[dict[str, Any]] = []
    max_width = int(os.environ.get("TRIPSTORY_VISION_FRAME_WIDTH", "640"))
    try:
        for window in windows:
            window_id = str(window.get("window_id") or "")
            for timestamp in window.get("frame_timestamps") or []:
                ts = max(0.0, _float(timestamp))
                capture.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                height, width = frame.shape[:2]
                if width > max_width:
                    scale = max_width / width
                    frame = cv2.resize(frame, (max_width, int(height * scale)))
                ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
                if not ok:
                    continue
                data = base64.b64encode(encoded.tobytes()).decode("ascii")
                frames.append(
                    {
                        "window_id": window_id,
                        "timestamp": round(ts, 2),
                        "url": f"data:image/jpeg;base64,{data}",
                    }
                )
    finally:
        capture.release()
    return frames


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _rate_limited_vision_post(payload: dict[str, Any], config: dict[str, str]) -> dict[str, Any] | None:
    global _last_vision_request_at
    min_interval = float(os.environ.get("TRIPSTORY_VISION_MIN_INTERVAL_SECONDS", "3"))
    max_retries = int(os.environ.get("TRIPSTORY_VISION_MAX_RETRIES", "2"))
    timeout = int(os.environ.get("TRIPSTORY_VISION_TIMEOUT", "75"))
    endpoint = config["base_url"]
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    with _vision_lock:
        for attempt in range(max_retries + 1):
            elapsed = time.monotonic() - _last_vision_request_at
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            prompt_chars = sum(
                len(str(part.get("text") or ""))
                for message in payload.get("messages") or []
                for part in (message.get("content") or [])
                if isinstance(part, dict)
            )
            image_count = sum(
                1
                for message in payload.get("messages") or []
                for part in (message.get("content") or [])
                if isinstance(part, dict) and part.get("type") == "image_url"
            )
            started = time.monotonic()
            log_event(
                logger,
                20,
                "vision_request_attempt",
                provider=config.get("provider"),
                model=config.get("model"),
                attempt=attempt + 1,
                max_retries=max_retries,
                input_chars=prompt_chars,
                approximate_input_tokens=approximate_tokens("x" * prompt_chars),
                image_count=image_count,
                max_output_tokens=payload.get("max_tokens"),
                stage="clip_analysis",
            )
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            request_elapsed = round(time.monotonic() - started, 3)
            _last_vision_request_at = time.monotonic()
            if response.status_code != 429:
                try:
                    response.raise_for_status()
                except requests.RequestException:
                    log_event(
                        logger,
                        40,
                        "vision_request_failed",
                        provider=config.get("provider"),
                        model=config.get("model"),
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        status_code=response.status_code,
                        elapsed_seconds=request_elapsed,
                        outcome="http_error",
                        stage="clip_analysis",
                    )
                    raise
                log_event(
                    logger,
                    20,
                    "vision_request_complete",
                    provider=config.get("provider"),
                    model=config.get("model"),
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    status_code=response.status_code,
                    elapsed_seconds=request_elapsed,
                    outcome="success",
                    stage="clip_analysis",
                )
                return response.json()
            retry_after = _float(response.headers.get("retry-after"))
            retry_delay = retry_after or min(30.0, (2**attempt) + random.random())
            log_event(
                logger,
                30,
                "vision_request_retry",
                provider=config.get("provider"),
                model=config.get("model"),
                attempt=attempt + 1,
                max_retries=max_retries,
                status_code=response.status_code,
                retry_delay_seconds=round(retry_delay, 3),
                elapsed_seconds=request_elapsed,
                outcome="retry",
                stage="clip_analysis",
            )
            time.sleep(retry_delay)
    log_event(
        logger,
        40,
        "vision_request_failed",
        provider=config.get("provider"),
        model=config.get("model"),
        max_retries=max_retries,
        status_code=response.status_code,
        outcome="rate_limited",
        stage="clip_analysis",
    )
    response.raise_for_status()
    return None


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:10]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_moment_descriptions(value: Any) -> list[dict[str, Any]]:
    normalized = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            normalized.append(
                {
                    "timestamp": round(_float(item.get("timestamp")), 2),
                    "description": str(item.get("description") or "").strip(),
                }
            )
        elif str(item).strip():
            normalized.append({"timestamp": 0.0, "description": str(item).strip()})
    return [item for item in normalized if item["description"]][:10]


def _trim_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rsplit(" ", 1)[0].strip() + "..."


def _normalize_vision_windows(value: Any, existing_windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {}
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        window_id = str(item.get("window_id") or "").strip()
        if window_id:
            by_id[window_id] = item

    enriched: list[dict[str, Any]] = []
    for window in existing_windows:
        next_window = dict(window)
        parsed = by_id.get(str(window.get("window_id") or ""))
        if parsed:
            evidence = (
                _trim_text(parsed.get("visual_evidence"))
                or _trim_text(parsed.get("summary"))
                or _trim_text(parsed.get("description"))
                or _trim_text(parsed.get("best_moment_description"))
            )
            if evidence:
                next_window["visual_evidence"] = evidence
            next_window["semantic_source"] = "vision"
            next_window["visible_subjects"] = _normalize_string_list(parsed.get("visible_subjects"))
            next_window["locations_or_scenes"] = _normalize_string_list(parsed.get("locations_or_scenes"))
            next_window["visible_actions"] = _normalize_string_list(parsed.get("actions") or parsed.get("visible_actions"))
            next_window["visual_mood"] = _trim_text(parsed.get("mood"), 120)
            next_window["avoid_reasons"] = _normalize_string_list(parsed.get("avoid_reasons"))
            best = parsed.get("best_moment_description")
            if isinstance(best, dict):
                next_window["best_moment_description"] = {
                    "timestamp": round(_float(best.get("timestamp") or window.get("start_time")), 2),
                    "description": _trim_text(best.get("description")),
                }
            elif _trim_text(best):
                next_window["best_moment_description"] = {
                    "timestamp": round(_float(parsed.get("best_frame_timestamp") or window.get("start_time")), 2),
                    "description": _trim_text(best),
                }
        enriched.append(next_window)
    return enriched


def _aggregate_window_strings(windows: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for window in windows:
        for value in window.get(key) or []:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values[:10]


def _window_moment_descriptions(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    descriptions: list[dict[str, Any]] = []
    for window in windows:
        best = window.get("best_moment_description")
        if isinstance(best, dict) and best.get("description"):
            descriptions.append(
                {
                    "timestamp": round(_float(best.get("timestamp") or window.get("start_time")), 2),
                    "description": _trim_text(best.get("description")),
                }
            )
            continue
        evidence = _trim_text(window.get("visual_evidence"))
        if evidence:
            descriptions.append(
                {
                    "timestamp": round(_float(window.get("start_time")), 2),
                    "description": evidence,
                }
            )
    return descriptions[:10]


def _vision_semantics(path: Path, analysis: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any] | None:
    config = _vision_provider_config()
    default_enabled = bool(config)
    if not _env_enabled("TRIPSTORY_ENABLE_VISION_ANALYSIS", default_enabled):
        return None
    if not config:
        return None
    smart_windows = [window for window in analysis.get("smart_windows") or [] if isinstance(window, dict)]
    max_windows = max(1, min(8, int(os.environ.get("TRIPSTORY_VISION_MAX_WINDOWS", "3"))))
    top_windows = smart_windows[:max_windows]
    frames = _window_frame_data_urls(path, top_windows) if top_windows else _frame_data_urls(path, _semantic_timestamps(analysis))
    if not frames:
        return None
    frame_map = [
        {"window_id": frame.get("window_id"), "timestamp": frame.get("timestamp")}
        for frame in frames
    ]
    prompt = {
        "task": "Analyze top candidate windows from one travel video clip for editing.",
        "frames": frame_map,
        "trip_context": context or {},
        "smart_windows": [
            {
                "window_id": window.get("window_id"),
                "start_time": window.get("start_time"),
                "duration": window.get("duration"),
                "score": window.get("score"),
                "opencv_evidence": window.get("visual_evidence"),
                "frame_timestamps": window.get("frame_timestamps"),
            }
            for window in top_windows
        ],
        "known_clip_metrics": {
            "duration_seconds": analysis.get("duration_seconds"),
            "quality_label": analysis.get("quality_label"),
            "face_count": analysis.get("face_count"),
            "scene_count": analysis.get("scene_count"),
            "transcript": analysis.get("transcript"),
        },
        "rules": [
            "Only describe visual/audio evidence that is present in the sampled frames or transcript.",
            "Do not invent landmarks, people, events, or emotions.",
            "Describe concrete visible content for each window, for example traveler speaking to camera, market street, shore birds, food stall, dark/shaky avoid.",
            "Return strict JSON with keys: summary, visible_subjects, locations_or_scenes, actions, mood, avoid_reasons, best_moment_descriptions, windows.",
            "windows must be an array with one object per window_id. Each object must include window_id, visual_evidence, visible_subjects, locations_or_scenes, actions, mood, avoid_reasons, and best_moment_description.",
            "best_moment_descriptions must be objects with timestamp and description.",
        ],
    }
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]
    for frame in frames:
        label = f"Frame for {frame.get('window_id') or 'clip'} at {frame['timestamp']}s"
        content.append({"type": "text", "text": label})
        content.append({"type": "image_url", "image_url": {"url": frame["url"], "detail": "low"}})
    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 700,
    }
    try:
        data = _rate_limited_vision_post(payload, config)
        message = ((data or {}).get("choices") or [{}])[0].get("message") or {}
        parsed = _extract_json_object(str(message.get("content") or ""))
        if not parsed:
            return None
        enriched_windows = _normalize_vision_windows(parsed.get("windows"), smart_windows)
        best_descriptions = _normalize_moment_descriptions(parsed.get("best_moment_descriptions")) or _window_moment_descriptions(enriched_windows)
        return {
            "semantic_source": config["semantic_source"],
            "semantic_summary": str(parsed.get("summary") or "").strip(),
            "visible_subjects": _normalize_string_list(parsed.get("visible_subjects")) or _aggregate_window_strings(enriched_windows, "visible_subjects"),
            "locations_or_scenes": _normalize_string_list(parsed.get("locations_or_scenes")) or _aggregate_window_strings(enriched_windows, "locations_or_scenes"),
            "visible_actions": _normalize_string_list(parsed.get("actions")) or _aggregate_window_strings(enriched_windows, "visible_actions"),
            "visual_mood": str(parsed.get("mood") or "").strip(),
            "avoid_reasons": _normalize_string_list(parsed.get("avoid_reasons")),
            "best_moment_descriptions": best_descriptions,
            "smart_windows": enriched_windows,
        }
    except Exception as exc:
        log_event(
            logger,
            30,
            "vision_analysis_unavailable",
            provider=config["provider"],
            model=config["model"],
            clip_name=path.name,
            exception_type=type(exc).__name__,
            outcome="heuristic_fallback",
            stage="clip_analysis",
        )
        logger.debug("Vision analysis exception", exc_info=True)
        return None


def _heuristic_semantics(analysis: dict[str, Any]) -> dict[str, Any]:
    subjects = ["people"] if analysis.get("face_count") else []
    if analysis.get("has_audio"):
        subjects.append("ambient audio or speech")
    scenes = [item.get("name") for item in analysis.get("named_landmarks") or [] if item.get("name")]
    if not scenes and analysis.get("scene_count"):
        scenes = ["travel scene"]
    avoid_reasons = []
    if analysis.get("quality_label") in {"dark", "overexposed", "soft or shaky"}:
        avoid_reasons.append(f"{analysis.get('quality_label')} image quality")
    windows = [window for window in analysis.get("smart_windows") or [] if isinstance(window, dict)]
    descriptions = _window_moment_descriptions(windows) or [
        {
            "timestamp": round(_float(timestamp), 2),
            "description": f"Detected strong moment in a {analysis.get('quality_label', 'usable')} travel clip.",
        }
        for timestamp in (analysis.get("best_moment_timestamps") or [])[:3]
    ]
    return {
        "semantic_source": "heuristic",
        "semantic_summary": _summary(analysis),
        "visible_subjects": subjects,
        "locations_or_scenes": scenes[:8],
        "visible_actions": [],
        "visual_mood": "",
        "avoid_reasons": avoid_reasons,
        "best_moment_descriptions": descriptions,
    }


def analyze_clip(path: str | Path, filename: str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    source = Path(path)
    started = time.monotonic()
    log_event(
        logger,
        20,
        "clip_analysis_start",
        clip_name=filename or source.name,
        stage="clip_analysis",
        outcome="started",
    )
    analysis: dict[str, Any] = {
        "filename": filename or source.name,
        "path": str(source),
        "status": "ok" if source.exists() else "missing",
    }
    if not source.exists() or source.suffix.lower() not in VIDEO_SUFFIXES:
        analysis.update({"summary": "No video analysis available.", "best_moment_timestamps": []})
        log_event(
            logger,
            30,
            "clip_analysis_skipped",
            clip_name=filename or source.name,
            status=analysis["status"],
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="skipped",
            stage="clip_analysis",
        )
        return analysis

    probe = _probe(source)
    visuals = _sample_visuals(source, probe.get("duration_seconds") or 0.0)
    audio = _audio_levels(source) if probe.get("has_audio") else {"mean_volume_db": None, "max_volume_db": None}
    transcript = _transcribe(source, bool(probe.get("has_audio")))
    analysis.update(probe)
    analysis.update(visuals)
    analysis.update(audio)
    analysis["transcript"] = transcript
    analysis["speech_detected"] = bool(transcript) or bool(probe.get("has_audio"))
    analysis["named_landmarks"] = _named_landmarks(analysis, context)
    analysis.update(_vision_semantics(source, analysis, context) or _heuristic_semantics(analysis))
    analysis["summary"] = _summary(analysis)
    log_event(
        logger,
        20,
        "clip_analysis_complete",
        clip_name=filename or source.name,
        duration_seconds=analysis.get("duration_seconds"),
        has_audio=analysis.get("has_audio"),
        semantic_source=analysis.get("semantic_source"),
        elapsed_seconds=round(time.monotonic() - started, 3),
        outcome="success",
        stage="clip_analysis",
    )
    return analysis


def analyze_clips(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [analyze_clip(item.get("path") or "", item.get("filename")) for item in items if item.get("path")]


def _summary(analysis: dict[str, Any]) -> str:
    parts = [
        f"{analysis.get('duration_seconds', 0)}s",
        f"{analysis.get('width', 0)}x{analysis.get('height', 0)}",
        f"{analysis.get('scene_count', 0)} scenes",
        f"{analysis.get('quality_label', 'unknown')} quality",
    ]
    if analysis.get("face_count"):
        parts.append(f"{analysis['face_count']} face hits")
    if analysis.get("has_audio"):
        parts.append("audio present")
    if analysis.get("transcript"):
        parts.append("speech transcribed")
    if analysis.get("semantic_source"):
        parts.append(f"{analysis.get('semantic_source')} semantic pass")
    if analysis.get("semantic_summary") and analysis.get("semantic_source") != "heuristic":
        parts.append(str(analysis.get("semantic_summary")))
    return ", ".join(parts)

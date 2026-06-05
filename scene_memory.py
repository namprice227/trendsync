from __future__ import annotations

import re
from typing import Any


ROLE_VALUES = ("hook", "setup", "progression", "payoff", "b_roll")


def _as_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _as_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 4)


def _safe_id(value: Any, fallback: str) -> str:
    raw = _as_text(value, fallback)
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    return cleaned[:80] or fallback


def _string_list(value: Any, limit: int = 8) -> list[str]:
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)][:limit]
    if _as_text(value):
        return [_as_text(value)]
    return []


def _quality_score(quality: str, window_score: float) -> float:
    quality_score = {
        "strong": 0.86,
        "usable": 0.64,
        "unknown": 0.45,
        "dark": 0.28,
        "overexposed": 0.26,
        "soft or shaky": 0.24,
    }.get(quality, 0.45)
    if window_score:
        return _bounded(window_score * 0.7 + quality_score * 0.3)
    return _bounded(quality_score)


def _audio_value(analysis: dict[str, Any], transcript: str) -> str:
    if transcript:
        return "high"
    if not analysis.get("has_audio"):
        return "none"
    mean_volume = analysis.get("mean_volume_db")
    if mean_volume is None:
        return "medium"
    volume = _as_float(mean_volume, -99.0)
    if volume > -22:
        return "medium"
    if volume > -38:
        return "low"
    return "low"


def _ambient_audio_value(analysis: dict[str, Any], transcript: str) -> str:
    if not analysis.get("has_audio"):
        return "none"
    if transcript:
        return "medium"
    return "medium" if _audio_value(analysis, transcript) in {"high", "medium"} else "low"


def _visual_value(score: float, quality: str, evidence: str) -> str:
    combined = _quality_score(quality, score)
    if combined >= 0.75 and evidence:
        return "high"
    if combined >= 0.45:
        return "medium"
    return "low"


def _role_candidates(
    scene_index: int,
    scene_count: int,
    analysis: dict[str, Any],
    window: dict[str, Any],
    transcript: str,
) -> list[str]:
    roles: list[str] = []
    score = _as_float(window.get("score"), 0.0)
    motion = _as_float(analysis.get("avg_motion"), 0.0)
    evidence = _as_text(window.get("visual_evidence") or analysis.get("semantic_summary")).lower()

    if scene_index == 0 or score >= 0.82:
        roles.append("hook")
    if transcript or any(word in evidence for word in ("arrive", "walking", "enter", "start", "made it")):
        roles.append("setup" if scene_index == 0 else "progression")
    if motion >= 18 or any(word in evidence for word in ("market", "street", "moving", "walk", "food", "stall")):
        roles.append("progression")
    if scene_index >= max(0, scene_count - 2):
        roles.append("payoff")
    roles.append("b_roll")

    unique = []
    for role in roles:
        if role in ROLE_VALUES and role not in unique:
            unique.append(role)
    return unique[:4] or ["b_roll"]


def _evidence_list(visual: str, transcript: str, window: dict[str, Any]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    if transcript:
        evidence.append({"type": "transcript", "value": transcript[:500]})
    if visual:
        evidence.append({"type": "visual", "value": visual[:500]})
    frame_times = window.get("frame_timestamps") or []
    if frame_times:
        evidence.append({"type": "frame_sample", "value": ", ".join(f"{_as_float(ts):.2f}s" for ts in frame_times[:4])})
    return evidence


def _risks(analysis: dict[str, Any], window: dict[str, Any], transcript: str) -> list[str]:
    risks: list[str] = []
    quality = _as_text(analysis.get("quality_label"), "unknown")
    if quality in {"dark", "overexposed", "soft or shaky"}:
        risks.append(f"visual quality is {quality}")
    if analysis.get("has_audio") and not transcript:
        risks.append("speech may exist but no transcript is available")
    if not window.get("semantic_source") and analysis.get("semantic_source") == "heuristic":
        risks.append("visual summary came from heuristic analysis")
    for reason in window.get("avoid_reasons") or []:
        text = _as_text(reason)
        if text:
            risks.append(text)
    return risks[:5]


def _scene_memory(
    project_id: str,
    item: dict[str, Any],
    window: dict[str, Any],
    scene_index: int,
    scene_count: int,
) -> dict[str, Any]:
    analysis = item.get("analysis") or {}
    clip_id = _safe_id(item.get("id") or item.get("filename"), f"clip_{scene_index + 1:03d}")
    window_id = _as_text(window.get("window_id"), f"win_{scene_index + 1:03d}")
    scene_id = f"{clip_id}_scene_{scene_index + 1:03d}"
    start = round(max(0.0, _as_float(window.get("start_time"), 0.0)), 2)
    duration = round(max(1.0, _as_float(window.get("duration"), 5.5)), 2)
    end = round(start + duration, 2)
    transcript = _as_text(analysis.get("transcript"))
    visual = (
        _as_text(window.get("visual_evidence"))
        or _as_text(window.get("semantic_summary"))
        or _as_text(analysis.get("semantic_summary"))
        or _as_text(analysis.get("summary"), "usable travel moment")
    )
    quality = _as_text(analysis.get("quality_label"), "unknown")
    score = _as_float(window.get("score"), 0.0)
    visual_score = _quality_score(quality, score)
    audio_value = _audio_value(analysis, transcript)
    role_candidates = _role_candidates(scene_index, scene_count, analysis, window, transcript)
    has_vlm = analysis.get("semantic_source") not in {None, "", "heuristic"} or window.get("semantic_source")
    grounding_confidence = visual_score * 0.55 + (0.25 if transcript else 0.0) + (0.15 if has_vlm else 0.05)

    return {
        "scene_id": scene_id,
        "project_id": project_id,
        "clip_id": clip_id,
        "clip_filename": _as_text(item.get("filename"), clip_id),
        "source_window_id": window_id,
        "time_range": {"start_sec": start, "end_sec": end},
        "transcript": transcript,
        "visual_summary": visual,
        "entities": _string_list(window.get("visible_subjects") or analysis.get("visible_subjects")),
        "actions": _string_list(window.get("visible_actions") or analysis.get("visible_actions")),
        "location": ", ".join(_string_list(window.get("locations_or_scenes") or analysis.get("locations_or_scenes"), 3)),
        "tone": _as_text(window.get("visual_mood") or analysis.get("visual_mood")),
        "audio_value": audio_value,
        "visual_value": _visual_value(score, quality, visual),
        "ambient_audio_value": _ambient_audio_value(analysis, transcript),
        "narrative_role_candidates": role_candidates,
        "story_energy": _bounded(score * 0.55 + visual_score * 0.35 + (0.1 if transcript else 0.0)),
        "grounding_confidence": _bounded(grounding_confidence),
        "evidence": _evidence_list(visual, transcript, window),
        "risks": _risks(analysis, window, transcript),
    }


def _fallback_window(analysis: dict[str, Any]) -> dict[str, Any]:
    duration = max(1.0, _as_float(analysis.get("duration_seconds"), 5.5))
    return {
        "window_id": "win_001",
        "start_time": 0.0,
        "duration": min(5.5, duration),
        "score": 0.25,
        "frame_timestamps": [0.0],
        "visual_evidence": _as_text(analysis.get("semantic_summary") or analysis.get("summary"), "usable travel moment"),
    }


def build_scene_memories(media_items: list[dict[str, Any]], project_id: str = "") -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    for item in media_items:
        analysis = item.get("analysis") or {}
        windows = [window for window in analysis.get("smart_windows") or [] if isinstance(window, dict)]
        if not windows:
            windows = [_fallback_window(analysis)]
        scene_count = len(windows)
        for index, window in enumerate(windows):
            memories.append(_scene_memory(project_id, item, window, index, scene_count))
    return memories


def compact_scene_manifest(scene_memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for scene in scene_memories:
        time_range = scene.get("time_range") or {}
        manifest.append(
            {
                "scene_id": scene.get("scene_id"),
                "clip_id": scene.get("clip_id"),
                "clip": scene.get("clip_filename"),
                "window_id": scene.get("source_window_id"),
                "start_sec": time_range.get("start_sec"),
                "end_sec": time_range.get("end_sec"),
                "visual_summary": scene.get("visual_summary"),
                "transcript_excerpt": _as_text(scene.get("transcript"))[:220],
                "entities": scene.get("entities") or [],
                "actions": scene.get("actions") or [],
                "location": scene.get("location"),
                "tone": scene.get("tone"),
                "audio_value": scene.get("audio_value"),
                "visual_value": scene.get("visual_value"),
                "ambient_audio_value": scene.get("ambient_audio_value"),
                "role_candidates": scene.get("narrative_role_candidates") or [],
                "story_energy": scene.get("story_energy"),
                "grounding_confidence": scene.get("grounding_confidence"),
                "risks": scene.get("risks") or [],
            }
        )
    return manifest

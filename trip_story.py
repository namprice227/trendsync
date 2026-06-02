from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any

from llm_provider import LLMProvider
from tripstory_logging import get_logger, log_event


LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "vi": "Vietnamese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
}

TECHNICAL_VOICEOVER_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)?s\b", re.IGNORECASE),
    re.compile(r"\b\d{3,5}x\d{3,5}\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+scenes?\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+face hits?\b", re.IGNORECASE),
    re.compile(r"\b(strong|usable|dark|overexposed|soft or shaky)\s+quality\b", re.IGNORECASE),
    re.compile(r"\baudio present\b", re.IGNORECASE),
    re.compile(r"\bthis moment shows\b", re.IGNORECASE),
    re.compile(r"\bthe places you explored\b", re.IGNORECASE),
)
GENERIC_VOICEOVER_PATTERNS = (
    re.compile(r"\b(this|that)\s+(trip|journey|memory|moment)\b", re.IGNORECASE),
    re.compile(r"\b(the|our|your)\s+(trip|journey|adventure|memories|moments)\b", re.IGNORECASE),
    re.compile(r"\bbeautiful\s+(place|places|moment|moments|memories)\b", re.IGNORECASE),
    re.compile(r"\bmemories?\s+(we|you)\s+(will|want to)\s+remember\b", re.IGNORECASE),
)
KEYWORD_STOPWORDS = {
    "about",
    "after",
    "again",
    "around",
    "because",
    "before",
    "camera",
    "clip",
    "clips",
    "detected",
    "during",
    "from",
    "into",
    "moment",
    "moments",
    "near",
    "quality",
    "scene",
    "selected",
    "shows",
    "that",
    "the",
    "this",
    "through",
    "travel",
    "trip",
    "usable",
    "video",
    "window",
    "with",
}
logger = get_logger("story")


class NonObjectStoryResponse(ValueError):
    pass


def _story_max_tokens() -> int:
    try:
        return max(512, int(os.environ.get("TRIPSTORY_STORY_MAX_TOKENS", "4096")))
    except ValueError:
        return 4096


def _language_name(code: str | None) -> str:
    if not code:
        return "English"
    return LANGUAGE_NAMES.get(code, code)


def _as_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return fallback


def _as_list(value: Any, fallback: list[Any] | None = None) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return list(fallback or [])
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return list(fallback or [])
        lines = [line.strip(" -•\t") for line in stripped.splitlines() if line.strip(" -•\t")]
        return lines or [stripped]
    if isinstance(value, dict):
        return [value]
    return list(fallback or [])


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _segment_id(index: int) -> str:
    return f"seg_{index + 1:03d}"


def _target_duration_seconds(render_options: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> float:
    render_options = render_options or {}
    context = context or {}
    value = render_options.get("target_duration_seconds") or context.get("target_duration_seconds") or 30
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 30.0
    return max(6.0, min(180.0, seconds))


def _include_title_card(render_options: dict[str, Any] | None = None) -> bool:
    if not render_options:
        return True
    return bool(render_options.get("include_title_card", True))


def _voiceover_budget(render_options: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> tuple[float, int]:
    target_seconds = _target_duration_seconds(render_options, context)
    title_seconds = 2.0 if _include_title_card(render_options) else 0.0
    voiceover_seconds = max(4.0, target_seconds - title_seconds)
    segment_count = max(1, min(30, math.ceil(voiceover_seconds / 5.5)))
    return voiceover_seconds, segment_count


def _normalize_clip_plan(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(_as_list(value, fallback)):
        if isinstance(item, dict):
            normalized.append(
                {
                    "clip_id": _as_text(item.get("clip_id")),
                    "clip": _as_text(item.get("clip"), f"clip_{index + 1}"),
                    "role": _as_text(item.get("role"), "trip memory"),
                    "suggested_use": _as_text(item.get("suggested_use"), "Use in the travel montage."),
                }
            )
        else:
            normalized.append(
                {
                    "clip_id": "",
                    "clip": _as_text(item, f"clip_{index + 1}"),
                    "role": "trip memory",
                    "suggested_use": _as_text(item, "Use in the travel montage."),
                }
            )
    return normalized or fallback


def _normalize_edit_decisions(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(_as_list(value, fallback)):
        if not isinstance(item, dict):
            item = {"reason": _as_text(item)}
        normalized.append(
            {
                "segment_id": _as_text(item.get("segment_id"), _segment_id(index)),
                "clip_id": _as_text(item.get("clip_id")),
                "clip": _as_text(item.get("clip"), f"clip_{index + 1}"),
                "window_id": _as_text(item.get("window_id")),
                "start_time": max(0.0, _as_float(item.get("start_time"), 0.0)),
                "duration": max(1.0, min(10.0, _as_float(item.get("duration"), 5.5))),
                "role": _as_text(item.get("role"), "story beat"),
                "reason": _as_text(item.get("reason"), "Selected by the smart edit planner."),
                "transition": _as_text(item.get("transition"), "fade"),
                "caption": _as_text(item.get("caption"), _as_text(item.get("clip"), f"Moment {index + 1}")),
                "audio_strategy": _as_text(item.get("audio_strategy"), "duck original ambience under narration"),
            }
        )
    return normalized or fallback


def _normalize_voiceover_segments(
    value: Any,
    fallback: list[dict[str, Any]],
    edit_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(_as_list(value, fallback)):
        decision = edit_decisions[index] if index < len(edit_decisions) else {}
        if isinstance(item, dict):
            voiceover = _as_text(item.get("voiceover") or item.get("text") or item.get("line"))
            caption = _as_text(item.get("caption"), _as_text(decision.get("caption"), f"Moment {index + 1}"))
            purpose = _as_text(item.get("purpose"), _as_text(decision.get("role"), "story beat"))
            normalized.append(
                {
                    "segment_id": _as_text(item.get("segment_id"), _as_text(decision.get("segment_id"), _segment_id(index))),
                    "clip_id": _as_text(item.get("clip_id"), _as_text(decision.get("clip_id"))),
                    "clip": _as_text(item.get("clip"), _as_text(decision.get("clip"), f"clip_{index + 1}")),
                    "window_id": _as_text(item.get("window_id"), _as_text(decision.get("window_id"))),
                    "start_time": max(0.0, _as_float(item.get("start_time"), _as_float(decision.get("start_time"), 0.0))),
                    "duration": max(1.0, min(10.0, _as_float(item.get("duration"), _as_float(decision.get("duration"), 5.5)))),
                    "voiceover": voiceover,
                    "caption": caption,
                    "purpose": purpose,
                }
            )
        else:
            normalized.append(
                {
                    "segment_id": _as_text(decision.get("segment_id"), _segment_id(index)),
                    "clip_id": _as_text(decision.get("clip_id")),
                    "clip": _as_text(decision.get("clip"), f"clip_{index + 1}"),
                    "window_id": _as_text(decision.get("window_id")),
                    "start_time": max(0.0, _as_float(decision.get("start_time"), 0.0)),
                    "duration": max(1.0, min(10.0, _as_float(decision.get("duration"), 5.5))),
                    "voiceover": _as_text(item),
                    "caption": _as_text(decision.get("caption"), f"Moment {index + 1}"),
                    "purpose": _as_text(decision.get("role"), "story beat"),
                }
            )
    normalized = [item for item in normalized if item.get("voiceover")]
    if not edit_decisions:
        return normalized or fallback

    fallback_by_id = {
        _as_text(item.get("segment_id")): item
        for item in fallback
        if isinstance(item, dict) and _as_text(item.get("segment_id"))
    }
    normalized_by_id = {
        _as_text(item.get("segment_id")): item
        for item in normalized
        if _as_text(item.get("segment_id"))
    }
    aligned: list[dict[str, Any]] = []
    for index, decision in enumerate(edit_decisions):
        segment_id = _as_text(decision.get("segment_id"), _segment_id(index))
        segment = normalized_by_id.get(segment_id)
        if segment is None and index < len(normalized):
            segment = normalized[index]
        if segment is None:
            segment = fallback_by_id.get(segment_id)
        if segment is None and index < len(fallback):
            segment = fallback[index]
        segment = dict(segment or {})
        aligned.append(
            {
                "segment_id": segment_id,
                "clip_id": _as_text(segment.get("clip_id"), _as_text(decision.get("clip_id"))),
                "clip": _as_text(segment.get("clip"), _as_text(decision.get("clip"), f"clip_{index + 1}")),
                "window_id": _as_text(segment.get("window_id"), _as_text(decision.get("window_id"))),
                "start_time": max(0.0, _as_float(decision.get("start_time"), _as_float(segment.get("start_time"), 0.0))),
                "duration": max(1.0, min(10.0, _as_float(decision.get("duration"), _as_float(segment.get("duration"), 5.5)))),
                "voiceover": _as_text(segment.get("voiceover")),
                "caption": _as_text(segment.get("caption"), _as_text(decision.get("caption"), f"Moment {index + 1}")),
                "purpose": _as_text(segment.get("purpose"), _as_text(decision.get("role"), "story beat")),
            }
        )
    return aligned or normalized or fallback


def _normalize_story_plan(plan: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(plan)
    normalized["title"] = _as_text(plan.get("title"), fallback["title"])
    normalized["language"] = _as_text(plan.get("language"), fallback["language"])
    normalized["tone"] = _as_text(plan.get("tone"), fallback["tone"])
    normalized["voiceover_script"] = _as_text(plan.get("voiceover_script"), fallback["voiceover_script"])
    normalized["narrative_arc"] = [_as_text(item) for item in _as_list(plan.get("narrative_arc"), fallback["narrative_arc"]) if _as_text(item)]
    normalized["edit_notes"] = [_as_text(item) for item in _as_list(plan.get("edit_notes"), fallback["edit_notes"]) if _as_text(item)]
    normalized["clip_plan"] = _normalize_clip_plan(plan.get("clip_plan"), fallback["clip_plan"])
    normalized["edit_decisions"] = _normalize_edit_decisions(plan.get("edit_decisions"), fallback["edit_decisions"])
    normalized["voiceover_segments"] = _normalize_voiceover_segments(
        plan.get("voiceover_segments"),
        fallback.get("voiceover_segments", []),
        normalized["edit_decisions"],
    )
    if not normalized["narrative_arc"]:
        normalized["narrative_arc"] = fallback["narrative_arc"]
    if not normalized["edit_notes"]:
        normalized["edit_notes"] = fallback["edit_notes"]
    segment_script = " ".join(item["voiceover"] for item in normalized["voiceover_segments"] if item.get("voiceover")).strip()
    normalized["voiceover_script"] = segment_script or normalized["voiceover_script"] or fallback["voiceover_script"]
    return normalized


def _brief_evidence(item: dict[str, Any], window: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis = item.get("analysis") or {}
    evidence = _window_evidence_text(window, _clip_evidence(item)) if window else _clip_evidence(item)
    return {
        "clip_id": _as_text(item.get("id")),
        "clip": _as_text(item.get("filename"), "clip"),
        "window_id": _as_text((window or {}).get("window_id")),
        "start_time": round(max(0.0, _as_float((window or {}).get("start_time"), 0.0)), 2),
        "reason": evidence,
        "quality": _as_text(analysis.get("quality_label"), "unknown"),
    }


def _fallback_creative_brief(
    context: dict[str, Any],
    media_items: list[dict[str, Any]],
    provider: LLMProvider,
    render_options: dict[str, Any] | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    destination = context.get("destination") or "this trip"
    audience = context.get("audience") or "friends and family"
    mood = context.get("mood") or "warm, cinematic, personal"
    candidate_evidence: list[dict[str, Any]] = []
    avoid: list[str] = []
    for item in media_items:
        analysis = item.get("analysis") or {}
        windows = [window for window in analysis.get("smart_windows") or [] if isinstance(window, dict)]
        if windows:
            candidate_evidence.extend(_brief_evidence(item, window) for window in windows[:2])
        else:
            candidate_evidence.append(_brief_evidence(item, None))
        if analysis.get("avoid_reasons"):
            avoid.extend(_as_text(reason) for reason in analysis.get("avoid_reasons") or [] if _as_text(reason))
        quality = _as_text(analysis.get("quality_label"))
        if quality in {"dark", "soft or shaky", "overexposed"}:
            avoid.append(f"Use {item.get('filename', 'clip')} carefully because it is {quality}.")
    candidate_evidence = candidate_evidence[:6]
    beat_sources = candidate_evidence[:3] or [{"reason": "uploaded clips", "clip": "clip"}]
    directions = [
        {
            "id": "direction_1",
            "title": "Personal memory",
            "angle": f"Frame {destination} as a memory built from the most specific observed moments.",
            "tone": mood,
            "audience": audience,
            "why": "This direction is safest because it follows visible clip evidence instead of inventing a travel-ad story.",
            "key_beats": [
                "Open with the clearest arrival or atmosphere shot.",
                "Move through the strongest people, place, food, or movement details.",
                "Close on the feeling the trip should leave behind.",
            ],
            "supporting_evidence": beat_sources,
        },
        {
            "id": "direction_2",
            "title": "Place-first recap",
            "angle": f"Let {destination} lead the story, with people and details as proof of being there.",
            "tone": "observational and cinematic",
            "audience": audience,
            "why": "This direction works when the clips have scenic or landmark evidence.",
            "key_beats": [
                "Start with the strongest location cue.",
                "Use motion or ambience to connect places.",
                "End with the most memorable view or quiet detail.",
            ],
            "supporting_evidence": beat_sources,
        },
    ]
    return {
        "title": f"{destination} producer brief",
        "summary": f"Plan a {int(round(_target_duration_seconds(render_options, context)))}-second recap for {audience}.",
        "recommended_direction_id": "direction_1",
        "selected_direction_id": "direction_1",
        "directions": directions,
        "questions": [
            {
                "id": "audience_intent",
                "label": "Audience",
                "question": "Who should this feel made for, and what should they understand by the end?",
                "why": "Audience changes the narration from private memory to social recap.",
                "answer": "",
            },
            {
                "id": "emotional_center",
                "label": "Feeling",
                "question": "What is the main feeling: funny, peaceful, romantic, proud, nostalgic, or something else?",
                "why": "The emotional center decides the hook and closing line.",
                "answer": "",
            },
            {
                "id": "must_use_or_avoid",
                "label": "Must use",
                "question": "Which moment must be included, and is there anything you do not want shown?",
                "why": "This prevents the editor from choosing a technically strong but personally wrong moment.",
                "answer": "",
            },
        ],
        "must_use": candidate_evidence[:4],
        "avoid": avoid[:5],
        "missing_context": [
            item
            for item in [
                "Add the personal reason this trip mattered." if not context.get("highlights") else "",
                "Add must-use or avoid moments before approving." if not context.get("notes") else "",
            ]
            if item
        ],
        "generation": {
            "llm_used": False,
            "llm_provider": provider.provider,
            "llm_model": provider.model,
            "llm_configured": provider.configured,
            "fallback_reason": fallback_reason or "LLM provider is not configured. TripStory drafted a local producer brief.",
        },
    }


def _normalize_creative_brief(plan: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(fallback)
    normalized.update(plan if isinstance(plan, dict) else {})
    normalized["title"] = _as_text(normalized.get("title"), fallback["title"])
    normalized["summary"] = _as_text(normalized.get("summary"), fallback["summary"])
    normalized["recommended_direction_id"] = _as_text(normalized.get("recommended_direction_id"), fallback["recommended_direction_id"])
    normalized["selected_direction_id"] = _as_text(normalized.get("selected_direction_id"), normalized["recommended_direction_id"])
    directions = []
    for index, item in enumerate(_as_list(normalized.get("directions"), fallback["directions"])):
        if not isinstance(item, dict):
            item = {"angle": _as_text(item)}
        direction_id = _as_text(item.get("id"), f"direction_{index + 1}")
        directions.append(
            {
                "id": direction_id,
                "title": _as_text(item.get("title"), f"Direction {index + 1}"),
                "angle": _as_text(item.get("angle"), "Tell the trip through the clearest observed moments."),
                "tone": _as_text(item.get("tone"), "warm and personal"),
                "audience": _as_text(item.get("audience"), "friends and family"),
                "why": _as_text(item.get("why"), "This direction is supported by the clip evidence."),
                "key_beats": [_as_text(beat) for beat in _as_list(item.get("key_beats"), []) if _as_text(beat)],
                "supporting_evidence": [
                    evidence if isinstance(evidence, dict) else {"reason": _as_text(evidence)}
                    for evidence in _as_list(item.get("supporting_evidence"), [])
                ],
            }
        )
    normalized["directions"] = directions[:3] or fallback["directions"]
    if normalized["selected_direction_id"] not in {item["id"] for item in normalized["directions"]}:
        normalized["selected_direction_id"] = normalized["recommended_direction_id"]
    questions = []
    for index, item in enumerate(_as_list(normalized.get("questions"), fallback["questions"])):
        if not isinstance(item, dict):
            item = {"question": _as_text(item)}
        questions.append(
            {
                "id": _as_text(item.get("id"), f"question_{index + 1}"),
                "label": _as_text(item.get("label"), f"Question {index + 1}"),
                "question": _as_text(item.get("question"), "What should the editor know before planning?"),
                "why": _as_text(item.get("why"), "This answer improves the creative brief."),
                "answer": _as_text(item.get("answer")),
            }
        )
    normalized["questions"] = questions[:3] or fallback["questions"]
    normalized["must_use"] = [
        item if isinstance(item, dict) else {"reason": _as_text(item)}
        for item in _as_list(normalized.get("must_use"), fallback.get("must_use", []))
    ][:6]
    normalized["avoid"] = [_as_text(item) for item in _as_list(normalized.get("avoid"), fallback.get("avoid", [])) if _as_text(item)][:6]
    normalized["missing_context"] = [
        _as_text(item)
        for item in _as_list(normalized.get("missing_context"), fallback.get("missing_context", []))
        if _as_text(item)
    ][:6]
    return normalized


def generate_creative_brief(
    context: dict[str, Any],
    media_items: list[dict[str, Any]],
    provider: LLMProvider | None = None,
    render_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = provider or LLMProvider()
    fallback = _fallback_creative_brief(context, media_items, provider, render_options)
    media_manifest = _clip_manifest(media_items)
    smart_windows = _smart_window_manifest(media_items)
    system = (
        "You are an AI producer for a travel-video editing tool. Draft a creative brief before final "
        "story generation. Do not write final voiceover. Ask only questions that materially improve the edit. "
        "Ground every proposal in observed clip evidence. Return strict JSON only."
    )
    user = {
        "trip_context": context,
        "clip_manifest": media_manifest,
        "smart_windows": smart_windows,
        "required_shape": {
            "title": "string",
            "summary": "string",
            "recommended_direction_id": "direction_1",
            "selected_direction_id": "direction_1",
            "directions": [
                {
                    "id": "direction_1",
                    "title": "string",
                    "angle": "string",
                    "tone": "string",
                    "audience": "string",
                    "why": "string",
                    "key_beats": ["string"],
                    "supporting_evidence": [{"clip_id": "string", "clip": "string", "window_id": "string", "reason": "string"}],
                }
            ],
            "questions": [{"id": "string", "label": "string", "question": "string", "why": "string", "answer": ""}],
            "must_use": [{"clip_id": "string", "clip": "string", "window_id": "string", "reason": "string"}],
            "avoid": ["string"],
            "missing_context": ["string"],
        },
        "requirements": [
            "Return exactly 2 or 3 directions.",
            "Return exactly 3 focused questions.",
            "Each direction must cite real clips or smart windows when evidence exists.",
            "Questions should cover audience, emotional center, and must-use or avoid moments.",
            "Do not write final narration, captions, edit_decisions, or voiceover_segments.",
        ],
    }
    if not provider.configured:
        return fallback
    try:
        started = time.monotonic()
        content = provider.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            max_tokens=max(1024, min(_story_max_tokens(), 3072)),
        )
        if not content:
            return _fallback_creative_brief(context, media_items, provider, render_options, "LLM returned an empty creative brief.")
        parsed = _parse_llm_story_json(content)
        brief = _normalize_creative_brief(parsed, fallback)
        brief["generation"] = {
            "llm_used": True,
            "llm_provider": provider.provider,
            "llm_model": provider.model,
            "llm_configured": provider.configured,
            "fallback_reason": None,
        }
        log_event(
            logger,
            20,
            "creative_brief_complete",
            provider=provider.provider,
            model=provider.model,
            clip_count=len(media_items),
            direction_count=len(brief.get("directions") or []),
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="llm",
            stage="creative_brief",
        )
        return brief
    except Exception as exc:
        log_event(
            logger,
            30,
            "creative_brief_fallback",
            provider=provider.provider,
            model=provider.model,
            exception_type=type(exc).__name__,
            outcome="local_fallback",
            stage="creative_brief",
        )
        return _fallback_creative_brief(context, media_items, provider, render_options, f"Creative brief LLM failed: {type(exc).__name__}.")


def _looks_like_editor_metadata(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in TECHNICAL_VOICEOVER_PATTERNS)


def _clean_voiceover_cue(value: str) -> str:
    text = " ".join(value.replace("\n", " ").split()).strip(" .")
    return text[:180] if text else ""


def _compact_text(value: Any, limit: int = 120) -> str:
    text = _as_text(value)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rsplit(" ", 1)[0].strip() + "..."


def _safe_creative_cue(value: Any, limit: int = 120) -> str:
    text = _compact_text(value, limit)
    return "" if _looks_like_editor_metadata(text) else text


def _motion_label(value: Any) -> str:
    motion = _as_float(value, 0.0)
    if motion >= 28:
        return "high"
    if motion >= 12:
        return "medium"
    if motion > 0:
        return "low"
    return ""


def _people_label(face_count: Any) -> str:
    count = int(_as_float(face_count, 0.0))
    if count >= 6:
        return "group"
    if count >= 1:
        return "visible"
    return "none"


def _timestamp_list(values: Any, limit: int = 3) -> str:
    timestamps = []
    for value in values or []:
        try:
            timestamps.append(f"{max(0.0, float(value)):.1f}s")
        except (TypeError, ValueError):
            continue
    return ",".join(timestamps[:limit])


def _clip_manifest_line(item: dict[str, Any], index: int) -> str:
    analysis = item.get("analysis") or {}
    clip_id = _compact_text(item.get("id") or item.get("filename") or f"clip_{index + 1}", 32)
    duration = int(round(_as_float(analysis.get("duration_seconds"), 0.0)))

    cue = (
        _safe_creative_cue(analysis.get("semantic_summary"), 100)
        or _safe_creative_cue((analysis.get("best_moment_descriptions") or [{}])[0].get("description") if analysis.get("best_moment_descriptions") else "", 100)
        or _safe_creative_cue(", ".join(str(value) for value in (analysis.get("locations_or_scenes") or [])[:2]), 80)
        or _safe_creative_cue(", ".join(str(value) for value in (analysis.get("visible_actions") or [])[:2]), 80)
        or _safe_creative_cue(analysis.get("transcript"), 100)
        or "travel moment"
    )

    parts = [f"[Clip {clip_id}] {duration}s", cue]
    people = _people_label(analysis.get("face_count"))
    if people != "none":
        parts.append(f"people:{people}")
    motion = _motion_label(analysis.get("avg_motion"))
    if motion:
        parts.append(f"motion:{motion}")
    if analysis.get("has_audio"):
        audio = "speech" if analysis.get("transcript") else "ambient"
        parts.append(f"audio:{audio}")
    best = _timestamp_list(analysis.get("best_moment_timestamps") or analysis.get("landmark_candidate_timestamps"))
    if best:
        parts.append(f"best:{best}")
    avoid = [
        _compact_text(reason, 32)
        for reason in (analysis.get("avoid_reasons") or [])
        if _compact_text(reason, 32)
    ]
    if avoid:
        parts.append(f"avoid:{','.join(avoid[:2])}")
    return " | ".join(parts)


def _clip_manifest(media_items: list[dict[str, Any]]) -> list[str]:
    return [_clip_manifest_line(item, index) for index, item in enumerate(media_items)]


def _window_evidence_text(window: dict[str, Any], fallback: str = "") -> str:
    candidates = [
        window.get("visual_evidence"),
        window.get("semantic_summary"),
        window.get("summary"),
    ]
    best = window.get("best_moment_description")
    if isinstance(best, dict):
        candidates.append(best.get("description"))
    candidates.extend(window.get("locations_or_scenes") or [])
    candidates.extend(window.get("visible_actions") or [])
    candidates.extend(window.get("visible_subjects") or [])
    for candidate in candidates:
        cleaned = _safe_creative_cue(candidate, 180)
        if cleaned:
            return cleaned
    return fallback


def _smart_window_manifest(media_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for index, item in enumerate(media_items):
        analysis = item.get("analysis") or {}
        clip_id = _as_text(item.get("id") or item.get("filename") or f"clip_{index + 1}")
        windows = []
        for window in analysis.get("smart_windows") or []:
            if not isinstance(window, dict):
                continue
            evidence = _window_evidence_text(window, _clip_evidence(item))
            windows.append(
                {
                    "window_id": _as_text(window.get("window_id"), f"win_{len(windows) + 1:03d}"),
                    "start_time": round(_as_float(window.get("start_time"), 0.0), 2),
                    "duration": round(max(1.0, min(10.0, _as_float(window.get("duration"), 5.5))), 2),
                    "score": round(max(0.0, min(1.0, _as_float(window.get("score"), 0.0))), 4),
                    "frame_timestamps": [
                        round(_as_float(timestamp, 0.0), 2)
                        for timestamp in (window.get("frame_timestamps") or [])[:4]
                    ],
                    "visual_evidence": evidence,
                    "avoid_reasons": [
                        _compact_text(reason, 64)
                        for reason in (window.get("avoid_reasons") or [])
                        if _compact_text(reason, 64)
                    ][:3],
                }
            )
        if not windows:
            best_times = analysis.get("best_moment_timestamps") or analysis.get("landmark_candidate_timestamps") or [0.0]
            for offset, timestamp in enumerate(best_times[:3]):
                windows.append(
                    {
                        "window_id": f"win_{offset + 1:03d}",
                        "start_time": max(0.0, round(_as_float(timestamp, 0.0) - 2.75, 2)),
                        "duration": 5.5,
                        "score": 0.25,
                        "frame_timestamps": [round(_as_float(timestamp, 0.0), 2)],
                        "visual_evidence": _clip_evidence(item),
                        "avoid_reasons": [],
                    }
                )
        manifest.append(
            {
                "clip_id": clip_id,
                "clip": _as_text(item.get("filename"), f"clip_{index + 1}"),
                "duration_seconds": round(_as_float(analysis.get("duration_seconds"), 0.0), 2),
                "semantic_summary": _safe_creative_cue(analysis.get("semantic_summary"), 140),
                "transcript_excerpt": _safe_creative_cue(analysis.get("transcript"), 140),
                "windows": windows[:8],
            }
        )
    return manifest


def _destination_name(context: dict[str, Any]) -> str:
    return _as_text(context.get("destination"), "the trip")


def _story_place_phrase(context: dict[str, Any]) -> str:
    places = _as_text(context.get("places_visited"))
    return places or _destination_name(context)


def _clip_evidence(item: dict[str, Any]) -> str:
    analysis = item.get("analysis") or {}
    if analysis.get("semantic_summary"):
        return _as_text(analysis.get("semantic_summary"))
    if analysis.get("best_moment_descriptions"):
        first = analysis["best_moment_descriptions"][0]
        if isinstance(first, dict) and first.get("description"):
            return _as_text(first.get("description"))
    if analysis.get("transcript"):
        return _as_text(analysis.get("transcript"))[:180]
    named = [landmark.get("name") for landmark in analysis.get("named_landmarks") or [] if landmark.get("name")]
    if named:
        return f"a moment connected to {', '.join(named[:3])}"
    return _as_text(analysis.get("summary"), f"the clip named {item.get('filename', 'this moment')}")


def _clip_voiceover_cue(item: dict[str, Any], window: dict[str, Any] | None = None) -> str:
    analysis = item.get("analysis") or {}
    candidates: list[str] = []
    if window:
        candidates.append(_window_evidence_text(window))
    for key in ("semantic_summary", "transcript"):
        if analysis.get(key):
            candidates.append(_as_text(analysis.get(key)))
    for moment in analysis.get("best_moment_descriptions") or []:
        if isinstance(moment, dict) and moment.get("description"):
            candidates.append(_as_text(moment.get("description")))
    scenes = [str(value).strip() for value in analysis.get("locations_or_scenes") or [] if str(value).strip()]
    actions = [str(value).strip() for value in analysis.get("visible_actions") or [] if str(value).strip()]
    subjects = [str(value).strip() for value in analysis.get("visible_subjects") or [] if str(value).strip()]
    named = [landmark.get("name") for landmark in analysis.get("named_landmarks") or [] if landmark.get("name")]
    if scenes:
        candidates.append(f"the atmosphere around {', '.join(scenes[:2])}")
    if actions:
        candidates.append(f"the movement and little details of {', '.join(actions[:2])}")
    if subjects:
        candidates.append(f"the faces, reactions, and energy in the moment")
    if named:
        candidates.append(f"the feeling around {', '.join(named[:2])}")
    for candidate in candidates:
        cleaned = _clean_voiceover_cue(candidate)
        if cleaned and not _looks_like_editor_metadata(cleaned):
            return cleaned
    if analysis.get("face_count"):
        return "the smiles and reactions that make the trip feel alive"
    if analysis.get("has_audio"):
        return "the sounds, movement, and tiny reactions you only notice when you are there"
    return "one of those blink-and-you-miss-it travel moments"


def _tiktok_voiceover_line(context: dict[str, Any], item: dict[str, Any], index: int, total: int, window: dict[str, Any] | None = None) -> str:
    destination = _destination_name(context)
    places = _story_place_phrase(context)
    cue = _clip_voiceover_cue(item, window)
    highlights = _clean_voiceover_cue(_as_text(context.get("highlights")))
    companions = _clean_voiceover_cue(_as_text(context.get("companions")))
    with_who = f" with {companions}" if companions and companions.lower() not in {"solo", "alone"} else ""

    if total <= 1:
        return f"POV: {destination} gives you the kind of memory you want to replay: {cue}."
    if index == 0:
        if highlights:
            return f"POV: you came to {destination} for {highlights}, but {cue} is what pulls you into the story."
        return f"POV: you came to {destination}{with_who}, and {cue} is where the trip starts to feel real."
    if index == total - 1:
        return f"And this is the part that stays with you: {cue}, one last little piece of {destination}."
    return f"Then {places} turns into something more personal: {cue}."


def _clip_for_segment(segment: dict[str, Any], media_items: list[dict[str, Any]], index: int) -> dict[str, Any]:
    ids = {str(segment.get("clip_id") or ""), str(segment.get("clip") or "")}
    for item in media_items:
        if {str(item.get("id") or ""), str(item.get("filename") or "")} & ids:
            return item
    return media_items[index] if index < len(media_items) else {}


def _window_for_segment(item: dict[str, Any], segment: dict[str, Any]) -> dict[str, Any] | None:
    window_id = str(segment.get("window_id") or "").strip()
    if not window_id:
        return None
    analysis = item.get("analysis") or {}
    for window in analysis.get("smart_windows") or []:
        if isinstance(window, dict) and str(window.get("window_id") or "") == window_id:
            return window
    return None


def _evidence_keywords(item: dict[str, Any], window: dict[str, Any] | None) -> set[str]:
    raw_parts = []
    if window:
        raw_parts.append(_window_evidence_text(window))
        raw_parts.extend(str(value) for value in window.get("locations_or_scenes") or [])
        raw_parts.extend(str(value) for value in window.get("visible_actions") or [])
        raw_parts.extend(str(value) for value in window.get("visible_subjects") or [])
    analysis = item.get("analysis") or {}
    raw_parts.append(analysis.get("semantic_summary") or "")
    raw_parts.extend(str(value) for value in analysis.get("locations_or_scenes") or [])
    raw_parts.extend(str(value) for value in analysis.get("visible_actions") or [])
    raw_parts.extend(str(value) for value in analysis.get("visible_subjects") or [])
    words = set()
    for part in raw_parts:
        for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", str(part).lower()):
            cleaned = word.strip("'-")
            if cleaned and cleaned not in KEYWORD_STOPWORDS:
                words.add(cleaned)
    return words


def _looks_generic_voiceover(text: str, item: dict[str, Any], window: dict[str, Any] | None) -> bool:
    if not text:
        return True
    if not any(pattern.search(text) for pattern in GENERIC_VOICEOVER_PATTERNS):
        return False
    keywords = _evidence_keywords(item, window)
    if not keywords:
        return True
    lowered = text.lower()
    return not any(keyword in lowered for keyword in list(keywords)[:20])


def _repair_voiceover_for_audience(plan: dict[str, Any], context: dict[str, Any], media_items: list[dict[str, Any]]) -> dict[str, Any]:
    segments = plan.get("voiceover_segments") if isinstance(plan.get("voiceover_segments"), list) else []
    repaired = []
    total = max(len(segments), len(media_items), 1)
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        item = _clip_for_segment(segment, media_items, index)
        window = _window_for_segment(item, segment)
        voiceover = _as_text(segment.get("voiceover"))
        if not voiceover or _looks_like_editor_metadata(voiceover) or _looks_generic_voiceover(voiceover, item, window):
            voiceover = _tiktok_voiceover_line(context, item, index, total, window)
        caption = _as_text(segment.get("caption"))
        if _looks_like_editor_metadata(caption):
            caption = _destination_name(context)
        repaired.append({**segment, "voiceover": voiceover, "caption": caption or _destination_name(context)})
    if not repaired and media_items:
        for index, item in enumerate(media_items):
            repaired.append(
                {
                    "clip_id": item.get("id"),
                    "clip": item.get("filename", f"clip_{index + 1}"),
                    "segment_id": _segment_id(index),
                    "window_id": "",
                    "start_time": 0.0,
                    "duration": 5.5,
                    "voiceover": _tiktok_voiceover_line(context, item, index, len(media_items)),
                    "caption": _destination_name(context),
                    "purpose": "story beat",
                }
            )
    if repaired:
        plan["voiceover_segments"] = repaired
        plan["voiceover_script"] = " ".join(segment["voiceover"] for segment in repaired if segment.get("voiceover")).strip()
    return plan


def _fallback_story(
    context: dict[str, Any],
    media_items: list[dict[str, Any]],
    render_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    destination = context.get("destination") or "your trip"
    duration = context.get("duration") or "a memorable holiday"
    places = context.get("places_visited") or destination
    mood = context.get("mood") or "warm, cinematic, and personal"
    audience = context.get("audience") or "friends and family"
    language = _language_name(context.get("language"))
    clip_count = len(media_items)
    voiceover_seconds, target_segment_count = _voiceover_budget(render_options, context)
    segment_duration = round(max(2.0, min(8.0, voiceover_seconds / target_segment_count)), 2)
    candidate_windows: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for item in media_items:
        windows = [window for window in (item.get("analysis") or {}).get("smart_windows") or [] if isinstance(window, dict)]
        if windows:
            candidate_windows.extend((item, window) for window in windows)
        else:
            candidate_windows.append((item, None))
    candidate_windows.sort(key=lambda pair: -_as_float((pair[1] or {}).get("score"), 0.0))
    planned_pairs = [candidate_windows[index % len(candidate_windows)] for index in range(target_segment_count)] if candidate_windows else []

    edit_decisions = []
    voiceover_segments = []
    for idx, (item, window) in enumerate(planned_pairs):
        analysis = item.get("analysis") or {}
        if window:
            start_time = max(0.0, _as_float(window.get("start_time"), 0.0))
            duration_seconds = max(1.0, min(10.0, _as_float(window.get("duration"), segment_duration)))
            window_id = _as_text(window.get("window_id"))
            evidence = _window_evidence_text(window, _clip_evidence(item))
        else:
            best_times = analysis.get("best_moment_timestamps") or analysis.get("landmark_candidate_timestamps") or [0]
            try:
                best_time = best_times[idx % len(best_times)] if best_times else 0
                start_time = max(0.0, float(best_time) - segment_duration / 2)
            except (TypeError, ValueError, IndexError):
                start_time = 0.0
            duration_seconds = segment_duration
            window_id = ""
            evidence = _clip_evidence(item)
        clip_duration = _as_float(analysis.get("duration_seconds"), 0.0)
        if clip_duration:
            start_time = min(start_time, max(0.0, clip_duration - duration_seconds))
        quality = analysis.get("quality_label") or "usable"
        clip_id = item.get("id") or item.get("filename", f"clip_{idx + 1}")
        clip_name = item.get("filename", f"clip_{idx + 1}")
        caption = item.get("filename", f"Moment {idx + 1}")
        role = "arrival" if idx == 0 else "memory beat"
        segment_id = _segment_id(idx)
        edit_decisions.append(
            {
                "segment_id": segment_id,
                "clip_id": clip_id,
                "clip": clip_name,
                "window_id": window_id,
                "start_time": round(start_time, 2),
                "duration": duration_seconds,
                "role": role,
                "reason": f"Fallback edit uses this {quality} window because analysis says: {evidence}",
                "transition": "fade",
                "caption": caption,
                "audio_strategy": "duck original ambience under narration",
            }
        )
        voiceover_segments.append(
            {
                "segment_id": segment_id,
                "clip_id": clip_id,
                "clip": clip_name,
                "window_id": window_id,
                "start_time": round(start_time, 2),
                "duration": duration_seconds,
                "voiceover": _tiktok_voiceover_line(context, item, idx, max(len(planned_pairs), 1), window),
                "caption": destination,
                "purpose": role,
            }
        )

    voiceover = " ".join(segment["voiceover"] for segment in voiceover_segments) or (
        f"This is the story of {duration} in {destination}. "
        f"We followed the day from arrival to discovery, through {places}, "
        f"and kept the small moments that made the journey feel alive. "
        f"For {audience}, this is not just a recap. It is a way to remember how the trip felt."
    )

    return {
        "title": f"{destination}: A Holiday Memory",
        "language": language,
        "tone": mood,
        "narrative_arc": [
            "Open with arrival and atmosphere.",
            "Move into the most meaningful places and shared moments.",
            "Close on the feeling you want to remember after the trip.",
        ],
        "voiceover_script": voiceover,
        "voiceover_segments": voiceover_segments,
        "edit_notes": [
            f"Use {clip_count} uploaded clip{'s' if clip_count != 1 else ''} in chronological order unless the user marks favorites.",
            "Keep transitions gentle and prioritize natural ambience under the voiceover.",
            "Let scenic clips breathe; cut faster only during movement, food, markets, or city walks.",
        ],
        "clip_plan": [
            {
                "clip_id": item.get("id"),
                "clip": item.get("filename", f"clip_{idx + 1}"),
                "role": "trip memory",
                "suggested_use": "Use as part of the chronological travel montage.",
            }
            for idx, item in enumerate(media_items)
        ],
        "edit_decisions": edit_decisions,
        "generation": {
            "llm_used": False,
            "llm_provider": "local",
            "llm_model": "local-fallback",
            "fallback_reason": "No configured LLM response was available.",
            "target_duration_seconds": _target_duration_seconds(render_options, context),
            "planned_voiceover_seconds": voiceover_seconds,
        },
    }


def _extract_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _parse_llm_story_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as original_error:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.IGNORECASE | re.DOTALL)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1).strip())
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, dict):
                    return parsed
                raise NonObjectStoryResponse("LLM returned a non-object JSON response.")
        balanced = _extract_balanced_json_object(stripped)
        if balanced and balanced != stripped:
            try:
                parsed = json.loads(balanced)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, dict):
                    return parsed
                raise NonObjectStoryResponse("LLM returned a non-object JSON response.")
        raise original_error
    if not isinstance(parsed, dict):
        raise NonObjectStoryResponse("LLM returned a non-object JSON response.")
    return parsed


def generate_trip_story(
    context: dict[str, Any],
    media_items: list[dict[str, Any]],
    provider: LLMProvider | None = None,
    render_options: dict[str, Any] | None = None,
    creative_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = provider or LLMProvider()
    language = _language_name(context.get("language"))
    fallback = _fallback_story(context, media_items, render_options)
    target_seconds = _target_duration_seconds(render_options, context)
    voiceover_seconds, target_segment_count = _voiceover_budget(render_options, context)
    fallback["generation"] = {
        "llm_used": False,
        "llm_provider": provider.provider,
        "llm_model": provider.model,
        "llm_configured": provider.configured,
        "fallback_reason": "LLM provider is not configured. Check TRIPSTORY_LLM_PROVIDER and provider API key in .env.",
        "target_duration_seconds": target_seconds,
        "planned_voiceover_seconds": voiceover_seconds,
    }

    media_manifest = _clip_manifest(media_items)
    smart_windows = _smart_window_manifest(media_items)

    system = (
        "You are a senior travel film editor and story producer. Build a concise, emotionally coherent "
        "holiday recap narrative from uploaded clips, user context, and machine clip intelligence. "
        "You must make concrete edit decisions, not generic advice. Ground every story beat in observed "
        "clip evidence such as semantic_summary, best_moment_descriptions, transcript, named_landmarks, "
        "visible_subjects, locations_or_scenes, quality, and timestamps. Never invent visuals that are not "
        "in the uploaded_media evidence. Return strict JSON only, with keys: title, language, tone, "
        "narrative_arc, voiceover_script, voiceover_segments, edit_notes, clip_plan, edit_decisions. "
        "The voiceover must be in the requested language."
    )
    # Incorporate pinned and excluded scenes (Milestone 2)
    excluded_clip_ids = render_options.get("excluded_clip_ids", []) if render_options else []
    pinned_clip_ids = render_options.get("favorite_clip_ids", []) if render_options else []

    # Filter the manifest to remove explicitly excluded clips
    filtered_media_manifest = [item for item in media_manifest if not any(item.startswith(exc_id) for exc_id in excluded_clip_ids)]
    filtered_smart_windows = [win for win in smart_windows if win.get("clip_id") not in excluded_clip_ids]

    user = {
        "target_language": language,
        "trip_context": context,
        "approved_creative_brief": creative_brief or None,
        "clip_manifest": media_manifest,
        "smart_windows": smart_windows,
        "manifest_rules": [
            "Each manifest line is compact: clip id, duration, creative visual cue, people/motion/audio hints, best timestamps, and avoid hints.",
            "Use smart_windows as the primary editing evidence. Each window has a stable window_id, start_time, duration, score, sampled frame_timestamps, and visual_evidence.",
            "Use only clip_manifest and smart_windows for story planning. Do not ask for or invent raw detector metadata.",
            "Best timestamps and frame_timestamps are source-clip seconds for edit choices; do not mention them in voiceover.",
        ],
        "requirements": [
            "Make the story feel personal, not like a generic travel ad.",
            "Assume clips may be imperfect phone footage.",
            f"Write for a {int(round(target_seconds))}-second rendered video.",
            "You MUST include ALL clips listed in the pinned_favorite_clip_ids in your final edit_decisions.",
            f"The title card uses 2 seconds when enabled, so edit_decisions should total about {voiceover_seconds:.1f} seconds.",
            f"Return about {target_segment_count} voiceover_segments, using repeated clips only when needed to fill the selected duration.",
            "Choose exact windows from smart_windows first. Prefer high score windows with concrete visual_evidence. Avoid weak/dark/shaky windows when alternatives exist.",
            "Use semantic_summary and smart window visual_evidence first when present. Use numeric analysis only as fallback evidence.",
            "Voiceover is audience-facing TikTok narration. It must sound natural, emotional, and watchable, not like metadata.",
            "Never put timestamps, seconds, resolution, scene counts, face counts, quality labels, filenames, or phrases like audio present in voiceover_script, voiceover_segments, or captions.",
            "Keep each voiceover segment punchy: one short sentence, usually 8-18 words, with a strong hook or emotional turn.",
            "Return edit_decisions as an ordered timeline. Each item must include segment_id, clip_id, clip, window_id, start_time, duration, role, reason, transition, caption, and audio_strategy.",
            "Each edit_decision must select an exact clip_id and window_id from smart_windows. Use the selected window's start_time and duration unless the clip is shorter.",
            "Return voiceover_segments in the same order and length as edit_decisions. Each segment must include segment_id, clip_id, clip, window_id, start_time, duration, voiceover, caption, and purpose.",
            "The segment_id in each voiceover_segments item must exactly match the paired edit_decisions item.",
            "Each voiceover segment must mention the actual visible content in the selected window, such as the shore birds, traveler speaking to camera, market street, food stall, or dark/shaky avoid. Do not write a generic trip summary unless no window evidence exists.",
            "The full voiceover_script must equal the ordered voiceover_segments joined together.",
            "Use start_time in seconds from the source clip. Choose durations between 2 and 8 seconds unless the clip analysis says the clip is shorter.",
            "For longer target durations, add more clip-specific narration beats instead of stretching one generic sentence.",
            "The reason field must explain why this exact clip segment belongs at that point in the story.",
            "Stay vendor neutral and do not mention a specific AI model.",
        ],
    }
    if creative_brief:
        user["requirements"].insert(0, "Follow the approved_creative_brief. Treat its selected direction, answers, must-use evidence, and avoid list as user-approved creative direction.")

    try:
        started = time.monotonic()
        manifest_chars = sum(len(line) for line in media_manifest)
        log_event(
            logger,
            20,
            "story_generation_start",
            provider=provider.provider,
            model=provider.model,
            configured=provider.configured,
            clip_count=len(media_items),
            manifest_chars=manifest_chars,
            language=language,
            stage="story_generation",
        )
        content = provider.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            max_tokens=_story_max_tokens(),
        )
        if not content:
            if provider.configured:
                fallback["generation"]["fallback_reason"] = (
                    f"{provider.provider} returned an empty response. "
                    "Increase TRIPSTORY_STORY_MAX_TOKENS or choose a model with a larger output budget."
                )
            log_event(
                logger,
                30,
                "story_generation_fallback",
                provider=provider.provider,
                model=provider.model,
                clip_count=len(media_items),
                elapsed_seconds=round(time.monotonic() - started, 3),
                fallback_reason="empty_llm_response",
                outcome="local_fallback",
                stage="story_generation",
            )
            return fallback
        parsed = _parse_llm_story_json(content)
        merged = _normalize_story_plan({**fallback, **parsed}, fallback)
        merged = _repair_voiceover_for_audience(merged, context, media_items)
        merged["generation"] = {
            "llm_used": True,
            "llm_provider": provider.provider,
            "llm_model": provider.model,
            "llm_configured": provider.configured,
            "fallback_reason": None,
            "target_duration_seconds": target_seconds,
            "planned_voiceover_seconds": voiceover_seconds,
        }
        log_event(
            logger,
            20,
            "story_generation_complete",
            provider=provider.provider,
            model=provider.model,
            clip_count=len(media_items),
            voiceover_segment_count=len(merged.get("voiceover_segments") or []),
            edit_decision_count=len(merged.get("edit_decisions") or []),
            smart_window_count=sum(len(item.get("windows") or []) for item in smart_windows),
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="llm",
            stage="story_generation",
        )
        return merged
    except json.JSONDecodeError as exc:
        fallback["generation"]["fallback_reason"] = (
            "LLM returned incomplete JSON, so TripStory used the local story fallback. "
            "Increase TRIPSTORY_STORY_MAX_TOKENS or choose a model with a larger output budget."
        )
        log_event(
            logger,
            30,
            "story_generation_fallback",
            provider=provider.provider,
            model=provider.model,
            clip_count=len(media_items),
            exception_type=type(exc).__name__,
            elapsed_seconds=round(time.monotonic() - started, 3) if "started" in locals() else None,
            fallback_reason="invalid_json",
            outcome="local_fallback",
            stage="story_generation",
        )
        logger.debug("Story generation returned invalid JSON", exc_info=True)
        return fallback
    except NonObjectStoryResponse as exc:
        fallback["generation"]["fallback_reason"] = "LLM returned a non-object JSON response."
        log_event(
            logger,
            30,
            "story_generation_fallback",
            provider=provider.provider,
            model=provider.model,
            clip_count=len(media_items),
            exception_type=type(exc).__name__,
            elapsed_seconds=round(time.monotonic() - started, 3) if "started" in locals() else None,
            fallback_reason="non_object_json",
            outcome="local_fallback",
            stage="story_generation",
        )
        logger.debug("Story generation returned a non-object response", exc_info=True)
        return fallback
    except Exception as exc:
        log_event(
            logger,
            30,
            "story_generation_fallback",
            provider=provider.provider,
            model=provider.model,
            clip_count=len(media_items),
            exception_type=type(exc).__name__,
            elapsed_seconds=round(time.monotonic() - started, 3) if "started" in locals() else None,
            outcome="local_fallback",
            stage="story_generation",
        )
        logger.debug("Story generation exception", exc_info=True)
        fallback["generation"]["fallback_reason"] = str(exc)
        return fallback

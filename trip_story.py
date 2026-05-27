from __future__ import annotations

import json
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
logger = get_logger("story")


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
                "clip_id": _as_text(item.get("clip_id")),
                "clip": _as_text(item.get("clip"), f"clip_{index + 1}"),
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
                    "clip_id": _as_text(item.get("clip_id"), _as_text(decision.get("clip_id"))),
                    "clip": _as_text(item.get("clip"), _as_text(decision.get("clip"), f"clip_{index + 1}")),
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
                    "clip_id": _as_text(decision.get("clip_id")),
                    "clip": _as_text(decision.get("clip"), f"clip_{index + 1}"),
                    "start_time": max(0.0, _as_float(decision.get("start_time"), 0.0)),
                    "duration": max(1.0, min(10.0, _as_float(decision.get("duration"), 5.5))),
                    "voiceover": _as_text(item),
                    "caption": _as_text(decision.get("caption"), f"Moment {index + 1}"),
                    "purpose": _as_text(decision.get("role"), "story beat"),
                }
            )
    normalized = [item for item in normalized if item.get("voiceover")]
    return normalized or fallback


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


def _clip_voiceover_cue(item: dict[str, Any]) -> str:
    analysis = item.get("analysis") or {}
    candidates: list[str] = []
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


def _tiktok_voiceover_line(context: dict[str, Any], item: dict[str, Any], index: int, total: int) -> str:
    destination = _destination_name(context)
    places = _story_place_phrase(context)
    cue = _clip_voiceover_cue(item)
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


def _repair_voiceover_for_audience(plan: dict[str, Any], context: dict[str, Any], media_items: list[dict[str, Any]]) -> dict[str, Any]:
    segments = plan.get("voiceover_segments") if isinstance(plan.get("voiceover_segments"), list) else []
    repaired = []
    total = max(len(segments), len(media_items), 1)
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        item = _clip_for_segment(segment, media_items, index)
        voiceover = _as_text(segment.get("voiceover"))
        if not voiceover or _looks_like_editor_metadata(voiceover):
            voiceover = _tiktok_voiceover_line(context, item, index, total)
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


def _fallback_story(context: dict[str, Any], media_items: list[dict[str, Any]]) -> dict[str, Any]:
    destination = context.get("destination") or "your trip"
    duration = context.get("duration") or "a memorable holiday"
    places = context.get("places_visited") or destination
    mood = context.get("mood") or "warm, cinematic, and personal"
    audience = context.get("audience") or "friends and family"
    language = _language_name(context.get("language"))
    clip_count = len(media_items)

    edit_decisions = []
    voiceover_segments = []
    for idx, item in enumerate(media_items):
        analysis = item.get("analysis") or {}
        best_times = analysis.get("best_moment_timestamps") or analysis.get("landmark_candidate_timestamps") or [0]
        try:
            start_time = max(0.0, float(best_times[0]) - 2.0)
        except (TypeError, ValueError, IndexError):
            start_time = 0.0
        quality = analysis.get("quality_label") or "usable"
        evidence = _clip_evidence(item)
        clip_id = item.get("id") or item.get("filename", f"clip_{idx + 1}")
        clip_name = item.get("filename", f"clip_{idx + 1}")
        caption = item.get("filename", f"Moment {idx + 1}")
        role = "arrival" if idx == 0 else "memory beat"
        edit_decisions.append(
            {
                "clip_id": clip_id,
                "clip": clip_name,
                "start_time": round(start_time, 2),
                "duration": 5.5,
                "role": role,
                "reason": f"Fallback edit uses this {quality} clip because analysis says: {evidence}",
                "transition": "fade",
                "caption": caption,
                "audio_strategy": "duck original ambience under narration",
            }
        )
        voiceover_segments.append(
            {
                "clip_id": clip_id,
                "clip": clip_name,
                "start_time": round(start_time, 2),
                "duration": 5.5,
                "voiceover": _tiktok_voiceover_line(context, item, idx, len(media_items)),
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
        },
    }


def generate_trip_story(
    context: dict[str, Any],
    media_items: list[dict[str, Any]],
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    provider = provider or LLMProvider()
    language = _language_name(context.get("language"))
    fallback = _fallback_story(context, media_items)
    fallback["generation"] = {
        "llm_used": False,
        "llm_provider": provider.provider,
        "llm_model": provider.model,
        "llm_configured": provider.configured,
        "fallback_reason": "LLM provider is not configured. Check TRIPSTORY_LLM_PROVIDER and provider API key in .env.",
    }

    media_manifest = _clip_manifest(media_items)

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
    user = {
        "target_language": language,
        "trip_context": context,
        "clip_manifest": media_manifest,
        "manifest_rules": [
            "Each manifest line is compact: clip id, duration, creative visual cue, people/motion/audio hints, best timestamps, and avoid hints.",
            "Use only the manifest for story planning. Do not ask for or invent raw detector metadata.",
            "Best timestamps are optional source-clip seconds for edit start choices; do not mention them in voiceover.",
        ],
        "requirements": [
            "Make the story feel personal, not like a generic travel ad.",
            "Assume clips may be imperfect phone footage.",
            "Keep voiceover suitable for a short 45-90 second video.",
            "Use semantic_summary and best_moment_descriptions first when present. Use numeric analysis only as fallback evidence.",
            "Use clip analysis to choose the best moments, avoid weak/dark/shaky sections when alternatives exist, and favor clips with faces, speech, scenic candidates, or strong quality labels.",
            "Voiceover is audience-facing TikTok narration. It must sound natural, emotional, and watchable, not like metadata.",
            "Never put timestamps, seconds, resolution, scene counts, face counts, quality labels, filenames, or phrases like audio present in voiceover_script, voiceover_segments, or captions.",
            "Keep each voiceover segment punchy: one short sentence, usually 8-18 words, with a strong hook or emotional turn.",
            "Return edit_decisions as an ordered timeline. Each item must include clip_id, clip, start_time, duration, role, reason, transition, caption, and audio_strategy.",
            "Return voiceover_segments in the same order and length as edit_decisions. Each segment must include clip_id, clip, start_time, duration, voiceover, caption, and purpose.",
            "Each voiceover segment must describe the actual selected clip segment. Do not write a generic trip summary unless no clip evidence exists.",
            "The full voiceover_script must equal the ordered voiceover_segments joined together.",
            "Use start_time in seconds from the source clip. Choose durations between 2 and 8 seconds unless the clip analysis says the clip is shorter.",
            "The reason field must explain why this exact clip segment belongs at that point in the story.",
            "Stay vendor neutral and do not mention a specific AI model.",
        ],
    }

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
            max_tokens=1800,
        )
        if not content:
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
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            fallback["generation"]["fallback_reason"] = "LLM returned a non-object JSON response."
            log_event(
                logger,
                30,
                "story_generation_fallback",
                provider=provider.provider,
                model=provider.model,
                clip_count=len(media_items),
                elapsed_seconds=round(time.monotonic() - started, 3),
                fallback_reason="non_object_json",
                outcome="local_fallback",
                stage="story_generation",
            )
            return fallback
        merged = _normalize_story_plan({**fallback, **parsed}, fallback)
        merged = _repair_voiceover_for_audience(merged, context, media_items)
        merged["generation"] = {
            "llm_used": True,
            "llm_provider": provider.provider,
            "llm_model": provider.model,
            "llm_configured": provider.configured,
            "fallback_reason": None,
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
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="llm",
            stage="story_generation",
        )
        return merged
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

from __future__ import annotations

import json
from typing import Any

from llm_provider import LLMProvider


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


def _language_name(code: str | None) -> str:
    if not code:
        return "English"
    return LANGUAGE_NAMES.get(code, code)


def _fallback_story(context: dict[str, Any], media_items: list[dict[str, Any]]) -> dict[str, Any]:
    destination = context.get("destination") or "your trip"
    duration = context.get("duration") or "a memorable holiday"
    places = context.get("places_visited") or "the places you explored"
    mood = context.get("mood") or "warm, cinematic, and personal"
    audience = context.get("audience") or "friends and family"
    language = _language_name(context.get("language"))
    clip_count = len(media_items)

    voiceover = (
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
        "edit_notes": [
            f"Use {clip_count} uploaded clip{'s' if clip_count != 1 else ''} in chronological order unless the user marks favorites.",
            "Keep transitions gentle and prioritize natural ambience under the voiceover.",
            "Let scenic clips breathe; cut faster only during movement, food, markets, or city walks.",
        ],
        "clip_plan": [
            {
                "clip": item.get("filename", f"clip_{idx + 1}"),
                "role": "trip memory",
                "suggested_use": "Use as part of the chronological travel montage.",
            }
            for idx, item in enumerate(media_items)
        ],
    }


def generate_trip_story(
    context: dict[str, Any],
    media_items: list[dict[str, Any]],
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    provider = provider or LLMProvider()
    language = _language_name(context.get("language"))
    fallback = _fallback_story(context, media_items)

    media_summary = [
        {
            "filename": item.get("filename"),
            "kind": item.get("kind"),
            "size_bytes": item.get("size_bytes"),
        }
        for item in media_items
    ]

    system = (
        "You are a travel film story producer. Build a concise, emotionally coherent "
        "holiday recap narrative from uploaded clips and user context. "
        "Return strict JSON only, with keys: title, language, tone, narrative_arc, "
        "voiceover_script, edit_notes, clip_plan. The voiceover must be in the requested language."
    )
    user = {
        "target_language": language,
        "trip_context": context,
        "uploaded_media": media_summary,
        "requirements": [
            "Make the story feel personal, not like a generic travel ad.",
            "Assume clips may be imperfect phone footage.",
            "Keep voiceover suitable for a short 45-90 second video.",
            "Stay vendor neutral and do not mention a specific AI model.",
        ],
    }

    try:
        content = provider.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            max_tokens=1100,
        )
        if not content:
            return fallback
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return fallback
        return {**fallback, **parsed}
    except Exception as exc:
        print(f"[trip_story] LLM unavailable, using fallback: {exc}")
        return fallback

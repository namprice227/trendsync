from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
import json
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm_provider import LLMProvider
from trip_renderer import render_trip_video
from trip_story import generate_trip_story


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"[api_server] Could not load {path}: {exc}")
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

MEDIA_ROOT = Path(os.environ.get("TRIPSTORY_MEDIA_DIR", "trip_sessions"))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
SESSION_STORE = Path(os.environ.get("TRIPSTORY_SESSION_STORE", str(MEDIA_ROOT.with_name(f"{MEDIA_ROOT.name}_sessions.json"))))

PHASE_SCREENS = {
    "collecting_context": "context",
    "uploading": "upload",
    "ready_to_plan": "context",
    "planning": "plan",
    "ready_to_render": "plan",
    "rendering": "output",
    "complete": "output",
    "error": "context",
}

app = FastAPI(
    title="TripStory API",
    description="Upload holiday media, collect trip context, and generate a multilingual narrative recap.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/files", StaticFiles(directory=str(MEDIA_ROOT)), name="files")

_lock = threading.RLock()
_sessions: dict[str, dict[str, Any]] = {}


class TripContextRequest(BaseModel):
    destination: str = Field("", max_length=200)
    duration: str = Field("", max_length=120)
    places_visited: str = Field("", max_length=1000)
    travel_dates: str = Field("", max_length=120)
    companions: str = Field("", max_length=300)
    highlights: str = Field("", max_length=1200)
    mood: str = Field("warm, cinematic, personal", max_length=200)
    audience: str = Field("friends and family", max_length=200)
    language: str = Field("en", max_length=40)
    notes: str = Field("", max_length=1500)
    llm_provider: str = Field("local", max_length=80)
    llm_model: str = Field("", max_length=200)


def _now() -> float:
    return round(time.time(), 3)


def _default_context() -> dict[str, str]:
    return {
        "destination": "",
        "duration": "",
        "places_visited": "",
        "travel_dates": "",
        "companions": "",
        "highlights": "",
        "mood": "warm, cinematic, personal",
        "audience": "friends and family",
        "language": "en",
        "notes": "",
        "llm_provider": "local",
        "llm_model": "",
    }


def _default_session(session_id: str | None = None) -> dict[str, Any]:
    now = _now()
    return {
        "id": session_id or uuid.uuid4().hex[:12],
        "phase": "collecting_context",
        "screen": "context",
        "next_action": "Upload your trip clips and answer a few context questions.",
        "created_at": now,
        "updated_at": now,
        "error": None,
        "progress_label": "Planning a holiday recap",
        "trip_context": _default_context(),
        "media_items": [],
        "recorded_clips": [],
        "story_plan": None,
        "script": None,
        "final_video_url": None,
        "story_json_url": None,
        "llm_provider": "local",
        "llm_model": os.environ.get("TRIPSTORY_LLM_MODEL", "local-fallback"),
    }


def _normalize_session(raw: dict[str, Any]) -> dict[str, Any]:
    session = _default_session(str(raw.get("id") or uuid.uuid4().hex[:12]))
    session.update(raw)
    context = _default_context()
    context.update(raw.get("trip_context") or {})
    context.pop("llm_api_key", None)
    session["trip_context"] = context
    session["media_items"] = list(raw.get("media_items") or [])
    session["recorded_clips"] = list(raw.get("recorded_clips") or [])
    if session.get("phase") in {"uploading", "planning", "rendering"}:
        session["phase"] = "error"
        session["progress_label"] = "Interrupted work"
        session["next_action"] = "The API restarted during background work. Retry the last action."
        session["error"] = session.get("error") or "Background task was interrupted by an API restart."
    session["screen"] = PHASE_SCREENS.get(session["phase"], "context")
    return session


def _save_sessions_locked() -> None:
    SESSION_STORE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SESSION_STORE.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(_sessions, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SESSION_STORE)


def _load_sessions() -> None:
    if not SESSION_STORE.exists():
        return
    try:
        data = json.loads(SESSION_STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[api_server] Could not load session store: {exc}")
        return
    if not isinstance(data, dict):
        return
    with _lock:
        for session_id, raw in data.items():
            if isinstance(raw, dict):
                _sessions[str(session_id)] = _normalize_session(raw)


_load_sessions()


def _session_dir(session_id: str) -> Path:
    path = MEDIA_ROOT / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name)
    return cleaned or fallback


def _public_url(session_id: str, path: str | Path) -> str:
    return f"/files/{session_id}/{Path(path).name}"


def _public_session(session_id: str) -> dict[str, Any]:
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        public = dict(session)
        public["screen"] = PHASE_SCREENS.get(public["phase"], "context")
        context = dict(public.get("trip_context") or {})
        context.pop("llm_api_key", None)
        public["trip_context"] = context
        return public


def _update_session(session_id: str, **updates: Any) -> dict[str, Any]:
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        session.update(updates)
        session["screen"] = PHASE_SCREENS.get(session["phase"], "context")
        session["updated_at"] = _now()
        _save_sessions_locked()
        return dict(session)


def _create_session() -> dict[str, Any]:
    session = _default_session()
    session_id = session["id"]
    with _lock:
        _sessions[session_id] = session
        _save_sessions_locked()
    _session_dir(session_id)
    return _public_session(session_id)


def _generate_story_background(session_id: str) -> None:
    try:
        session = _public_session(session_id)
        media_items = list(session.get("media_items") or [])
        if not media_items:
            raise ValueError("Upload at least one clip or video before generating the story.")

        context = dict(session.get("trip_context") or {})
        provider = LLMProvider(
            provider=context.get("llm_provider") or "local",
            model=context.get("llm_model") or None,
        )
        plan = generate_trip_story(context, media_items, provider)
        _update_session(
            session_id,
            phase="ready_to_render",
            progress_label="Narrative ready",
            next_action="Review the voiceover and render the recap video.",
            story_plan=plan,
            script=plan.get("voiceover_script"),
            llm_model=provider.model,
            llm_provider=provider.provider,
        )
    except Exception as exc:
        _update_session(
            session_id,
            phase="error",
            progress_label="Story planning failed",
            next_action="Adjust the context or upload media, then try again.",
            error=str(exc),
        )


def _render_background(session_id: str) -> None:
    try:
        session = _public_session(session_id)
        clips = list(session.get("recorded_clips") or [])
        story_plan = session.get("story_plan")
        if not clips:
            raise ValueError("Upload at least one video before rendering.")
        if not story_plan:
            raise ValueError("Generate a narrative plan before rendering.")

        session_dir = _session_dir(session_id)
        output_path = session_dir / "holiday_recap.mp4"
        story_path = session_dir / "story_plan.json"

        _update_session(
            session_id,
            phase="rendering",
            progress_label="Rendering holiday recap",
            next_action="I am stitching the uploaded clips and saving the voiceover plan.",
            error=None,
        )

        rendered_path = render_trip_video(clips, story_plan, str(output_path), metadata_path=str(story_path))
        _update_session(
            session_id,
            phase="complete",
            progress_label="Holiday recap ready",
            next_action="Review the final video and use the saved voiceover script for narration or TTS.",
            final_video_url=_public_url(session_id, rendered_path),
            story_json_url=_public_url(session_id, story_path),
        )
    except Exception as exc:
        _update_session(
            session_id,
            phase="error",
            progress_label="Render failed",
            next_action="Check the uploaded files and try rendering again.",
            error=str(exc),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "TripStory"}


@app.post("/sessions")
def create_session() -> dict[str, Any]:
    return _create_session()


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    return _public_session(session_id)


@app.post("/sessions/{session_id}/context")
def save_context(session_id: str, request: TripContextRequest) -> dict[str, Any]:
    _public_session(session_id)
    context = request.model_dump()
    media_count = len(_public_session(session_id).get("media_items") or [])
    phase = "ready_to_plan" if media_count > 0 and context.get("destination") else "collecting_context"
    next_action = (
        "Generate the narrative plan when the context feels complete."
        if phase == "ready_to_plan"
        else "Upload media and add where you went before generating the story."
    )
    return _update_session(
        session_id,
        phase=phase,
        progress_label="Trip context saved",
        next_action=next_action,
        trip_context=context,
        llm_provider=context.get("llm_provider") or "local",
        llm_model=context.get("llm_model") or os.environ.get("TRIPSTORY_LLM_MODEL", "local-fallback"),
        error=None,
    )


@app.post("/sessions/{session_id}/media")
async def upload_media(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    session = _public_session(session_id)
    if not files:
        raise HTTPException(status_code=400, detail="No media uploaded.")

    _update_session(
        session_id,
        phase="uploading",
        progress_label="Receiving trip media",
        next_action="Saving your clips and videos.",
        error=None,
    )

    media_dir = _session_dir(session_id) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    media_items = list(session.get("media_items") or [])
    clips = list(session.get("recorded_clips") or [])
    start_idx = len(media_items)

    for offset, upload in enumerate(files):
        suffix = Path(upload.filename or "").suffix or ".mp4"
        filename = _safe_name(upload.filename or f"clip_{start_idx + offset}{suffix}", f"clip_{start_idx + offset}{suffix}")
        target = media_dir / f"{start_idx + offset:03d}_{filename}"
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)

        kind = "video" if suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"} else "clip"
        item = {
            "id": uuid.uuid4().hex[:10],
            "filename": filename,
            "kind": kind,
            "path": str(target),
            "url": f"/files/{session_id}/media/{target.name}",
            "size_bytes": target.stat().st_size,
        }
        media_items.append(item)
        if kind == "video":
            clips.append(str(target))

    context = dict(session.get("trip_context") or {})
    phase = "ready_to_plan" if context.get("destination") else "collecting_context"
    return _update_session(
        session_id,
        phase=phase,
        progress_label=f"{len(media_items)} media item{'s' if len(media_items) != 1 else ''} uploaded",
        next_action="Add trip context, then generate the narrative plan.",
        media_items=media_items,
        recorded_clips=clips,
        error=None,
    )


@app.post("/sessions/{session_id}/generate-story")
def generate_story(session_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    session = _public_session(session_id)
    if not session.get("media_items"):
        raise HTTPException(status_code=409, detail="Upload media before generating the story.")
    background_tasks.add_task(_generate_story_background, session_id)
    return _update_session(
        session_id,
        phase="planning",
        progress_label="Writing travel narrative",
        next_action="The model is turning your trip context into a voiceover plan.",
        error=None,
    )


@app.post("/sessions/{session_id}/render")
def render_session(session_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    session = _public_session(session_id)
    if not session.get("story_plan"):
        raise HTTPException(status_code=409, detail="Generate a narrative plan before rendering.")
    if not session.get("recorded_clips"):
        raise HTTPException(status_code=409, detail="Upload at least one video clip before rendering.")
    background_tasks.add_task(_render_background, session_id)
    return _update_session(
        session_id,
        phase="rendering",
        progress_label="Queued render",
        next_action="The recap video is being assembled.",
        error=None,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("TRIPSTORY_API_PORT", "8010")))

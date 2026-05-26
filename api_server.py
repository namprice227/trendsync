from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
import uuid
import json
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm_provider import LLMProvider
from media_intelligence import analyze_clip, vision_semantics_source
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
SESSION_DB = Path(os.environ.get("TRIPSTORY_SESSION_DB", str(MEDIA_ROOT.with_name(f"{MEDIA_ROOT.name}.sqlite3"))))
MAX_UPLOAD_BYTES = int(os.environ.get("TRIPSTORY_MAX_UPLOAD_MB", "512")) * 1024 * 1024
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}

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


def _init_db() -> None:
    SESSION_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SESSION_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                data TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_owner_updated ON sessions(owner_id, updated_at DESC)")
        conn.commit()


def _auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
    x_tripstory_token: str | None = Header(default=None),
    x_tripstory_user: str | None = Header(default=None),
) -> dict[str, str]:
    expected = os.environ.get("TRIPSTORY_AUTH_TOKEN", "").strip()
    provided = (x_tripstory_token or "").strip()
    if not provided and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer":
            provided = token.strip()
    if expected and provided != expected:
        raise HTTPException(status_code=401, detail="Invalid TripStory API token.")
    owner = x_tripstory_user or request.headers.get("x-tripstory-owner") or "local"
    safe_owner = "".join(ch if ch.isalnum() or ch in ("-", "_", "@", ".") else "_" for ch in owner)[:120]
    return {"owner_id": safe_owner or "local"}


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
    llm_provider: str = Field("deepseek", max_length=80)
    llm_model: str = Field("", max_length=200)


class RenderRequest(BaseModel):
    aspect_ratio: str = Field("original", max_length=40)
    clip_order: list[str] = Field(default_factory=list)
    favorite_clip_ids: list[str] = Field(default_factory=list)
    burn_captions: bool = False
    include_title_card: bool = True
    include_music_bed: bool = False


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
        "llm_provider": "deepseek",
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
        "owner_id": "local",
        "share_token": None,
        "error": None,
        "progress_label": "Planning a holiday recap",
        "progress_percent": 0,
        "events": [],
        "trip_context": _default_context(),
        "media_items": [],
        "recorded_clips": [],
        "clip_analysis": [],
        "story_plan": None,
        "script": None,
        "final_video_url": None,
        "voiceover_audio_url": None,
        "story_json_url": None,
        "edit_decisions_url": None,
        "caption_srt_url": None,
        "caption_vtt_url": None,
        "render_options": RenderRequest().model_dump(),
        "llm_provider": "deepseek",
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
    session["clip_analysis"] = list(raw.get("clip_analysis") or [])
    session["events"] = list(raw.get("events") or [])
    render_options = RenderRequest().model_dump()
    render_options.update(raw.get("render_options") or {})
    session["render_options"] = render_options
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
    _init_db()
    with sqlite3.connect(SESSION_DB) as conn:
        for session_id, session in _sessions.items():
            conn.execute(
                """
                INSERT INTO sessions (id, owner_id, created_at, updated_at, data)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    data=excluded.data
                """,
                (
                    session_id,
                    session.get("owner_id") or "local",
                    float(session.get("created_at") or _now()),
                    float(session.get("updated_at") or _now()),
                    json.dumps(session, ensure_ascii=False),
                ),
            )
        conn.commit()


def _load_sessions() -> None:
    data: dict[str, Any] = {}
    if SESSION_DB.exists():
        try:
            with sqlite3.connect(SESSION_DB) as conn:
                rows = conn.execute("SELECT id, data FROM sessions").fetchall()
            data = {row[0]: json.loads(row[1]) for row in rows}
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            print(f"[api_server] Could not load session database: {exc}")
            data = {}
    if not data and SESSION_STORE.exists():
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


def _event(session_id: str, label: str, progress_percent: int | None = None, level: str = "info") -> None:
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            return
        events = list(session.get("events") or [])
        events.append({"at": _now(), "level": level, "label": label})
        session["events"] = events[-80:]
        if progress_percent is not None:
            session["progress_percent"] = max(0, min(100, progress_percent))
        session["updated_at"] = _now()
        _save_sessions_locked()


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


def _ensure_owner(session: dict[str, Any], owner_id: str) -> None:
    if (session.get("owner_id") or "local") != owner_id:
        raise HTTPException(status_code=404, detail="Session not found")


def _owner_from_auth(auth: Any) -> str:
    return auth.get("owner_id", "local") if isinstance(auth, dict) else "local"


def _create_session(owner_id: str = "local") -> dict[str, Any]:
    session = _default_session()
    session["owner_id"] = owner_id
    session_id = session["id"]
    with _lock:
        _sessions[session_id] = session
        _save_sessions_locked()
    _session_dir(session_id)
    return _public_session(session_id)


def _vision_requested() -> bool:
    return bool(vision_semantics_source())


def _ensure_current_clip_analysis(session_id: str, media_items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Refresh analysis before planning when semantic evidence was not available at upload time."""

    refreshed = False
    for item in media_items:
        path = Path(str(item.get("path") or ""))
        analysis = item.get("analysis") or {}
        expected_source = vision_semantics_source()
        needs_semantics = not analysis.get("semantic_source") or (expected_source and analysis.get("semantic_source") != expected_source)
        if not path.exists() or not needs_semantics:
            continue
        item["analysis"] = analyze_clip(path, item.get("filename"), context=context)
        refreshed = True
    if refreshed:
        _update_session(
            session_id,
            media_items=media_items,
            clip_analysis=[item["analysis"] for item in media_items if item.get("analysis")],
        )
    return media_items


def _generate_story_background(session_id: str) -> None:
    try:
        session = _public_session(session_id)
        media_items = list(session.get("media_items") or [])
        if not media_items:
            raise ValueError("Upload at least one clip or video before generating the story.")

        _event(session_id, "Analyzing trip brief and clip intelligence", 35)
        context = dict(session.get("trip_context") or {})
        media_items = _ensure_current_clip_analysis(session_id, media_items, context)
        selected_provider = (context.get("llm_provider") or "").strip().lower()
        provider_name = selected_provider if selected_provider and selected_provider != "local" else None
        provider = LLMProvider(
            provider=provider_name,
            model=context.get("llm_model") or None,
        )
        if provider.configured:
            _event(session_id, f"Calling {provider.provider} LLM for voiceover and smart edit decisions", 45)
        else:
            _event(session_id, f"Using local fallback because {provider.provider} is not configured", 45, level="warning")
        plan = generate_trip_story(context, media_items, provider)
        generation = plan.get("generation") or {}
        _event(
            session_id,
            f"Narrative plan generated with {'LLM' if generation.get('llm_used') else 'local fallback'}",
            90,
            level="info" if generation.get("llm_used") else "warning",
        )
        _update_session(
            session_id,
            phase="ready_to_render",
            progress_label="Narrative ready",
            next_action="Review the voiceover and render the recap video.",
            story_plan=plan,
            script=plan.get("voiceover_script"),
            llm_model=provider.model,
            llm_provider=provider.provider,
            progress_percent=100,
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
        narration_path = session_dir / "voiceover.mp3"
        captions_srt_path = session_dir / "captions.srt"
        captions_vtt_path = session_dir / "captions.vtt"
        edit_decisions_path = session_dir / "edit_decisions.json"
        render_options = dict(session.get("render_options") or {})

        _update_session(
            session_id,
            phase="rendering",
            progress_label="Rendering holiday recap",
            next_action="I am stitching the clips, generating narration when TTS is configured, and mixing the final audio.",
            progress_percent=10,
            error=None,
        )
        _event(session_id, "Preparing story-aware render", 15)

        rendered_path = render_trip_video(
            clips,
            story_plan,
            str(output_path),
            metadata_path=str(story_path),
            narration_path=str(narration_path),
            media_items=list(session.get("media_items") or []),
            render_options=render_options,
            context=dict(session.get("trip_context") or {}),
            captions_srt_path=str(captions_srt_path),
            captions_vtt_path=str(captions_vtt_path),
        )
        _event(session_id, "Render finished", 95)
        _update_session(
            session_id,
            phase="complete",
            progress_label="Holiday recap ready",
            next_action="Review the final video. If TTS was configured, the voiceover is mixed into the render.",
            final_video_url=_public_url(session_id, rendered_path),
            voiceover_audio_url=_public_url(session_id, narration_path) if narration_path.exists() else None,
            story_json_url=_public_url(session_id, story_path),
            edit_decisions_url=_public_url(session_id, edit_decisions_path) if edit_decisions_path.exists() else None,
            caption_srt_url=_public_url(session_id, captions_srt_path) if captions_srt_path.exists() else None,
            caption_vtt_url=_public_url(session_id, captions_vtt_path) if captions_vtt_path.exists() else None,
            progress_percent=100,
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


@app.get("/sessions")
def list_sessions(auth: dict[str, str] = Depends(_auth_context)) -> dict[str, Any]:
    owner_id = _owner_from_auth(auth)
    with _lock:
        sessions = [
            _public_session(session_id)
            for session_id, session in _sessions.items()
            if (session.get("owner_id") or "local") == owner_id
        ]
    sessions.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
    return {
        "sessions": [
            {
                "id": session["id"],
                "destination": session.get("trip_context", {}).get("destination") or "Untitled trip",
                "phase": session["phase"],
                "updated_at": session["updated_at"],
                "media_count": len(session.get("media_items") or []),
                "final_video_url": session.get("final_video_url"),
                "share_token": session.get("share_token"),
            }
            for session in sessions
        ]
    }


@app.post("/sessions")
def create_session(auth: dict[str, str] = Depends(_auth_context)) -> dict[str, Any]:
    return _create_session(_owner_from_auth(auth))


@app.get("/sessions/{session_id}")
def get_session(session_id: str, auth: dict[str, str] = Depends(_auth_context)) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    return session


@app.post("/sessions/{session_id}/context")
def save_context(session_id: str, request: TripContextRequest, auth: dict[str, str] = Depends(_auth_context)) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
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
    auth: dict[str, str] = Depends(_auth_context),
) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
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
    context = dict(session.get("trip_context") or {})

    for offset, upload in enumerate(files):
        suffix = Path(upload.filename or "").suffix or ".mp4"
        if suffix.lower() not in ALLOWED_VIDEO_SUFFIXES:
            raise HTTPException(status_code=415, detail=f"Unsupported upload type: {suffix or 'unknown'}")
        filename = _safe_name(upload.filename or f"clip_{start_idx + offset}{suffix}", f"clip_{start_idx + offset}{suffix}")
        target = media_dir / f"{start_idx + offset:03d}_{filename}"
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        if target.stat().st_size > MAX_UPLOAD_BYTES:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=413, detail=f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

        kind = "video"
        item = {
            "id": uuid.uuid4().hex[:10],
            "filename": filename,
            "kind": kind,
            "path": str(target),
            "url": f"/files/{session_id}/media/{target.name}",
            "size_bytes": target.stat().st_size,
        }
        if kind == "video":
            item["analysis"] = analyze_clip(target, filename, context=context)
        media_items.append(item)
        if kind == "video":
            clips.append(str(target))

    clip_analysis = [item["analysis"] for item in media_items if item.get("analysis")]
    phase = "ready_to_plan" if context.get("destination") else "collecting_context"
    return _update_session(
        session_id,
        phase=phase,
        progress_label=f"{len(media_items)} media item{'s' if len(media_items) != 1 else ''} uploaded and analyzed",
        next_action="Review the clip intelligence, add trip context, then generate the narrative plan.",
        media_items=media_items,
        recorded_clips=clips,
        clip_analysis=clip_analysis,
        error=None,
    )


@app.post("/sessions/{session_id}/generate-story")
def generate_story(
    session_id: str,
    background_tasks: BackgroundTasks,
    auth: dict[str, str] = Depends(_auth_context),
) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    if not session.get("media_items"):
        raise HTTPException(status_code=409, detail="Upload media before generating the story.")
    background_tasks.add_task(_generate_story_background, session_id)
    return _update_session(
        session_id,
        phase="planning",
        progress_label="Writing travel narrative",
        next_action="The model is turning your trip context into a voiceover plan.",
        progress_percent=10,
        error=None,
    )


@app.post("/sessions/{session_id}/render")
def render_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    request: RenderRequest | None = None,
    auth: dict[str, str] = Depends(_auth_context),
) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    if not session.get("story_plan"):
        raise HTTPException(status_code=409, detail="Generate a narrative plan before rendering.")
    if not session.get("recorded_clips"):
        raise HTTPException(status_code=409, detail="Upload at least one video clip before rendering.")
    render_options = request.model_dump() if request else dict(session.get("render_options") or RenderRequest().model_dump())
    _update_session(session_id, render_options=render_options)
    background_tasks.add_task(_render_background, session_id)
    return _update_session(
        session_id,
        phase="rendering",
        progress_label="Queued render",
        next_action="The recap video is being assembled.",
        progress_percent=5,
        error=None,
    )


@app.post("/sessions/{session_id}/share")
def share_session(session_id: str, auth: dict[str, str] = Depends(_auth_context)) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    token = session.get("share_token") or uuid.uuid4().hex
    updated = _update_session(session_id, share_token=token)
    return {"share_token": token, "share_url": f"/share/{token}", "session": updated}


@app.get("/share/{share_token}")
def get_shared_session(share_token: str) -> dict[str, Any]:
    with _lock:
        for session_id, session in _sessions.items():
            if session.get("share_token") == share_token:
                return _public_session(session_id)
    raise HTTPException(status_code=404, detail="Shared project not found")


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, auth: dict[str, str] = Depends(_auth_context)) -> dict[str, str]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    with _lock:
        _sessions.pop(session_id, None)
        _save_sessions_locked()
        if SESSION_DB.exists():
            with sqlite3.connect(SESSION_DB) as conn:
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                conn.commit()
    shutil.rmtree(MEDIA_ROOT / session_id, ignore_errors=True)
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("TRIPSTORY_API_PORT", "8010")))

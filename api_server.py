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

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm_provider import LLMProvider
from media_intelligence import analyze_clip, vision_semantics_source
from trip_renderer import render_trip_video
from trip_story import generate_trip_story
from tripstory_logging import configure_logging, get_logger, http_request_logging_enabled, log_event


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        get_logger("api").warning("dotenv_load_failed %s", json.dumps({"path": str(path), "exception_type": type(exc).__name__}))
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
configure_logging()
logger = get_logger("api")

MEDIA_ROOT = Path(os.environ.get("TRIPSTORY_MEDIA_DIR", "trip_sessions"))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
SESSION_STORE = Path(os.environ.get("TRIPSTORY_SESSION_STORE", str(MEDIA_ROOT.with_name(f"{MEDIA_ROOT.name}_sessions.json"))))
SESSION_DB = Path(os.environ.get("TRIPSTORY_SESSION_DB", str(MEDIA_ROOT.with_name(f"{MEDIA_ROOT.name}.sqlite3"))))
MAX_UPLOAD_BYTES = int(os.environ.get("TRIPSTORY_MAX_UPLOAD_MB", "512")) * 1024 * 1024
SQLITE_TIMEOUT_SECONDS = float(os.environ.get("TRIPSTORY_SQLITE_TIMEOUT_SECONDS", "20.0"))
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
ACTIVE_JOB_STATES = {
    "queued",
    "analyzing",
    "planning",
    "preparing",
    "rendering_segments",
    "writing_captions",
    "synthesizing_narration",
    "mixing_audio",
}
DEFAULT_STALE_JOB_SECONDS = int(os.environ.get("TRIPSTORY_STALE_JOB_SECONDS", str(int(os.environ.get("TRIPSTORY_JOB_TIMEOUT_SECONDS", "3600")) + 300)))

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


def _connect_db() -> sqlite3.Connection:
    SESSION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SESSION_DB, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.execute(f"PRAGMA busy_timeout = {int(SQLITE_TIMEOUT_SECONDS * 1000)}")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _extract_request_ids(path: str) -> dict[str, str]:
    parts = [part for part in path.split("/") if part]
    fields: dict[str, str] = {}
    if len(parts) >= 2 and parts[0] in {"sessions", "files"}:
        fields["session_id"] = parts[1]
    if len(parts) >= 4 and parts[0] == "sessions" and parts[2] == "jobs":
        fields["job_id"] = parts[3]
    return fields


def _http_scope_fields(scope: dict[str, Any]) -> dict[str, Any]:
    path = str(scope.get("path") or "")
    client = scope.get("client")
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    fields: dict[str, Any] = {
        "method": scope.get("method"),
        "path": path,
        "client_host": client[0] if client else None,
        "content_length": headers.get("content-length"),
    }
    fields.update(_extract_request_ids(path))
    return fields


def _route_path(scope: dict[str, Any]) -> str | None:
    route = scope.get("route")
    return getattr(route, "path", None)


def _session_status_fields(path: str, status_code: int) -> dict[str, Any]:
    ids = _extract_request_ids(path)
    session_id = ids.get("session_id")
    if not session_id or not path.startswith("/sessions/") or status_code >= 400:
        return {}
    try:
        session = _public_session(session_id)
    except HTTPException:
        return {}
    active_job = session.get("active_job") or {}
    fields: dict[str, Any] = {
        "session_phase": session.get("phase"),
        "session_screen": session.get("screen"),
        "session_progress_percent": session.get("progress_percent"),
        "media_count": len(session.get("media_items") or []),
        "events_count": len(session.get("events") or []),
        "final_video_ready": bool(session.get("final_video_url")),
    }
    if active_job:
        fields.update(
            active_job_id=active_job.get("id"),
            active_job_type=active_job.get("type"),
            active_job_state=active_job.get("state"),
            active_job_progress_percent=active_job.get("progress_percent"),
            active_job_step=active_job.get("current_step"),
        )
    return fields


class HTTPRequestLogMiddleware:
    def __init__(self, app: Any) -> None:
        self.wrapped_app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not http_request_logging_enabled():
            await self.wrapped_app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:8]
        started = time.monotonic()
        base_fields = {"request_id": request_id, **_http_scope_fields(scope)}
        completed = False
        log_event(logger, 10, "http_request_start", **base_fields)

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal completed
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 0)
                level = 40 if status_code >= 500 else 30 if status_code >= 400 else 20
                complete_fields = {
                    **base_fields,
                    "route": _route_path(scope),
                    "status_code": status_code,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                    "outcome": "success" if status_code < 400 else "error",
                }
                complete_fields.update(_session_status_fields(str(scope.get("path") or ""), status_code))
                log_event(logger, level, "http_request_complete", **complete_fields)
                completed = True
            await send(message)

        try:
            await self.wrapped_app(scope, receive, send_wrapper)
        except Exception as exc:
            log_event(
                logger,
                40,
                "http_request_failed",
                **base_fields,
                elapsed_ms=round((time.monotonic() - started) * 1000, 1),
                exception_type=type(exc).__name__,
                outcome="hard_failure",
            )
            raise
        if not completed:
            log_event(
                logger,
                30,
                "http_request_complete",
                **base_fields,
                route=_route_path(scope),
                elapsed_ms=round((time.monotonic() - started) * 1000, 1),
                outcome="missing_response_start",
            )


app.add_middleware(HTTPRequestLogMiddleware)


def _init_db() -> None:
    with _connect_db() as conn:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                state TEXT NOT NULL,
                progress_percent INTEGER NOT NULL,
                current_step TEXT NOT NULL,
                error TEXT,
                rq_job_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session_updated ON jobs(session_id, updated_at DESC)")
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


def _timestamp(value: Any, fallback: float | None = None) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback if fallback is not None else _now()


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
    session["created_at"] = _timestamp(session.get("created_at"))
    session["updated_at"] = _timestamp(session.get("updated_at"), session["created_at"])
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
    if session.get("phase") == "uploading":
        session["phase"] = "error"
        session["progress_label"] = "Interrupted work"
        session["next_action"] = "The API restarted during background work. Retry the last action."
        session["error"] = session.get("error") or "Background task was interrupted by an API restart."
    session["screen"] = PHASE_SCREENS.get(session["phase"], "context")
    return session


def _read_session_from_db(session_id: str) -> dict[str, Any] | None:
    if not SESSION_DB.exists():
        return None
    try:
        with _connect_db() as conn:
            row = conn.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _refresh_session_from_db_locked(session_id: str) -> None:
    raw = _read_session_from_db(session_id)
    if not raw:
        return
    incoming = _normalize_session(raw)
    current = _sessions.get(session_id)
    if current is None or float(incoming.get("updated_at") or 0) > float(current.get("updated_at") or 0):
        _sessions[session_id] = incoming


def _refresh_sessions_from_db_locked() -> None:
    if not SESSION_DB.exists():
        return
    try:
        with _connect_db() as conn:
            rows = conn.execute("SELECT id, data FROM sessions").fetchall()
    except sqlite3.Error:
        return
    for session_id, raw_data in rows:
        try:
            raw = json.loads(raw_data)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            incoming = _normalize_session(raw)
            current = _sessions.get(str(session_id))
            if current is None or float(incoming.get("updated_at") or 0) > float(current.get("updated_at") or 0):
                _sessions[str(session_id)] = incoming


def _save_sessions_locked() -> None:
    _refresh_sessions_from_db_locked()
    SESSION_STORE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SESSION_STORE.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(_sessions, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SESSION_STORE)
    _init_db()
    with _connect_db() as conn:
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
            with _connect_db() as conn:
                rows = conn.execute("SELECT id, data FROM sessions").fetchall()
            data = {row[0]: json.loads(row[1]) for row in rows}
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            log_event(logger, 30, "session_database_load_failed", path=str(SESSION_DB), exception_type=type(exc).__name__, outcome="fallback_to_json")
            data = {}
    if not data and SESSION_STORE.exists():
        try:
            data = json.loads(SESSION_STORE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log_event(logger, 30, "session_store_load_failed", path=str(SESSION_STORE), exception_type=type(exc).__name__, outcome="empty_sessions")
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


def _row_to_job(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    keys = (
        "id",
        "session_id",
        "type",
        "state",
        "progress_percent",
        "current_step",
        "error",
        "rq_job_id",
        "attempts",
        "created_at",
        "updated_at",
    )
    return {key: row[index] for index, key in enumerate(keys)}


def _create_job(session_id: str, job_type: str, current_step: str) -> dict[str, Any]:
    _init_db()
    job_id = uuid.uuid4().hex[:12]
    now = _now()
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, session_id, type, state, progress_percent, current_step, error, rq_job_id, attempts, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?, ?)
            """,
            (job_id, session_id, job_type, "queued", 0, current_step, now, now),
        )
        conn.commit()
    return _get_job(job_id)


def _get_job(job_id: str) -> dict[str, Any]:
    _init_db()
    with _connect_db() as conn:
        row = conn.execute(
            """
            SELECT id, session_id, type, state, progress_percent, current_step, error, rq_job_id, attempts, created_at, updated_at
            FROM jobs
            WHERE id = ?
            """,
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_job(row)


def _latest_active_job(session_id: str) -> dict[str, Any] | None:
    _init_db()
    placeholders = ",".join("?" for _ in ACTIVE_JOB_STATES)
    with _connect_db() as conn:
        row = conn.execute(
            f"""
            SELECT id, session_id, type, state, progress_percent, current_step, error, rq_job_id, attempts, created_at, updated_at
            FROM jobs
            WHERE session_id = ? AND state IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (session_id, *ACTIVE_JOB_STATES),
        ).fetchone()
    if not row:
        return None
    job = _row_to_job(row)
    if _job_is_stale(job):
        _expire_stale_job(job)
        return None
    return job


def _job_is_stale(job: dict[str, Any]) -> bool:
    stale_after = max(60, DEFAULT_STALE_JOB_SECONDS)
    return (_now() - float(job.get("updated_at") or 0)) > stale_after


def _expire_stale_job(job: dict[str, Any]) -> None:
    job_id = str(job.get("id") or "")
    session_id = str(job.get("session_id") or "")
    job_type = str(job.get("type") or "job")
    if not job_id or not session_id:
        return
    message = f"{job_type.replace('_', ' ').title()} interrupted before completion."
    log_event(
        logger,
        30,
        "stale_job_expired",
        session_id=session_id,
        job_id=job_id,
        job_type=job_type,
        previous_state=job.get("state"),
        previous_step=job.get("current_step"),
        stale_seconds=round(_now() - float(job.get("updated_at") or 0), 1),
        outcome="marked_failed",
    )
    _update_job(job_id, state="failed", current_step=message, error=message)
    with _lock:
        _refresh_session_from_db_locked(session_id)
        session = _sessions.get(session_id)
        if not session or session.get("phase") not in {"planning", "rendering"}:
            return
        session["phase"] = "error"
        session["screen"] = PHASE_SCREENS["error"]
        session["progress_label"] = message
        session["next_action"] = "Start Redis and the TripStory worker, then retry the action."
        session["error"] = message
        session["updated_at"] = _now()
        _save_sessions_locked()


def _update_job(job_id: str, **updates: Any) -> dict[str, Any]:
    allowed = {"state", "progress_percent", "current_step", "error", "rq_job_id", "attempts"}
    fields = []
    values: list[Any] = []
    for key, value in updates.items():
        if key not in allowed:
            continue
        fields.append(f"{key} = ?")
        values.append(value)
    if not fields:
        return _get_job(job_id)
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(job_id)
    _init_db()
    with _connect_db() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    return _get_job(job_id)


def _job_progress(job_id: str | None, session_id: str, state: str, step: str, progress_percent: int) -> None:
    log_event(
        logger,
        20,
        "job_progress",
        session_id=session_id,
        job_id=job_id,
        state=state,
        stage=state,
        progress_percent=max(0, min(100, progress_percent)),
        step=step,
    )
    if job_id:
        _update_job(job_id, state=state, current_step=step, progress_percent=max(0, min(100, progress_percent)), error=None)
    _event(session_id, step, progress_percent)


def _enqueue_rq_job(job_id: str) -> str:
    try:
        from redis import Redis
        from rq import Queue
        from worker import run_tripstory_job
    except ImportError as exc:
        raise RuntimeError("RQ queue backend requires redis and rq packages. Run pip install -r requirements.txt.") from exc

    redis_url = os.environ.get("TRIPSTORY_REDIS_URL", "redis://localhost:6379/0")
    queue_name = os.environ.get("TRIPSTORY_QUEUE_NAME", "tripstory")
    timeout = int(os.environ.get("TRIPSTORY_JOB_TIMEOUT_SECONDS", "3600"))
    connection = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=connection)
    rq_job = queue.enqueue(run_tripstory_job, job_id, job_timeout=timeout)
    log_event(logger, 20, "rq_job_enqueued", job_id=job_id, rq_job_id=str(rq_job.id), queue_name=queue_name, timeout_seconds=timeout, outcome="success")
    return str(rq_job.id)


def _enqueue_job(session_id: str, job_type: str) -> dict[str, Any]:
    step = "Queued story generation" if job_type == "story_generation" else "Queued render"
    job = _create_job(session_id, job_type, step)
    log_event(logger, 20, "job_created", session_id=session_id, job_id=job["id"], job_type=job_type, state="queued", step=step)
    backend = os.environ.get("TRIPSTORY_QUEUE_BACKEND", "rq").strip().lower()
    if backend == "inline":
        run_queued_job(job["id"])
        return _get_job(job["id"])
    if backend != "rq":
        raise HTTPException(status_code=500, detail=f"Unsupported queue backend: {backend}")
    try:
        rq_job_id = _enqueue_rq_job(job["id"])
        return _update_job(job["id"], rq_job_id=rq_job_id)
    except Exception as exc:
        logger.exception("Queue enqueue failed")
        log_event(logger, 40, "job_enqueue_failed", session_id=session_id, job_id=job["id"], job_type=job_type, exception_type=type(exc).__name__, outcome="hard_failure")
        _update_job(job["id"], state="failed", current_step="Queue enqueue failed", error=str(exc))
        _update_session(
            session_id,
            phase="error",
            progress_label="Queue enqueue failed",
            next_action="Start Redis and the TripStory worker, then retry the action.",
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=f"Could not enqueue job: {exc}") from exc


def _public_session(session_id: str) -> dict[str, Any]:
    with _lock:
        _refresh_session_from_db_locked(session_id)
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        active_job = _latest_active_job(session_id)
        if active_job is None:
            _refresh_session_from_db_locked(session_id)
            session = _sessions.get(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")
        public = dict(session)
        public["screen"] = PHASE_SCREENS.get(public["phase"], "context")
        context = dict(public.get("trip_context") or {})
        context.pop("llm_api_key", None)
        public["trip_context"] = context
        public["active_job"] = active_job
        return public


def _event(session_id: str, label: str, progress_percent: int | None = None, level: str = "info") -> None:
    with _lock:
        _refresh_session_from_db_locked(session_id)
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
        _refresh_session_from_db_locked(session_id)
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
    log_event(logger, 20, "session_created", session_id=session_id, owner_id=owner_id)
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
        analysis_started = time.monotonic()
        log_event(logger, 20, "clip_analysis_refresh_start", session_id=session_id, clip_id=item.get("id"), clip_name=item.get("filename"), stage="clip_analysis")
        item["analysis"] = analyze_clip(path, item.get("filename"), context=context)
        log_event(
            logger,
            20,
            "clip_analysis_refresh_complete",
            session_id=session_id,
            clip_id=item.get("id"),
            clip_name=item.get("filename"),
            semantic_source=(item.get("analysis") or {}).get("semantic_source"),
            elapsed_seconds=round(time.monotonic() - analysis_started, 3),
            stage="clip_analysis",
            outcome="success",
        )
        refreshed = True
    if refreshed:
        _update_session(
            session_id,
            media_items=media_items,
            clip_analysis=[item["analysis"] for item in media_items if item.get("analysis")],
        )
    return media_items


def _generate_story_background(session_id: str, job_id: str | None = None) -> None:
    started = time.monotonic()
    try:
        log_event(logger, 20, "story_job_start", session_id=session_id, job_id=job_id, stage="story_generation")
        session = _public_session(session_id)
        media_items = list(session.get("media_items") or [])
        if not media_items:
            raise ValueError("Upload at least one clip or video before generating the story.")

        _job_progress(job_id, session_id, "analyzing", "Analyzing trip brief and clip intelligence", 35)
        context = dict(session.get("trip_context") or {})
        media_items = _ensure_current_clip_analysis(session_id, media_items, context)
        selected_provider = (context.get("llm_provider") or "").strip().lower()
        provider_name = selected_provider if selected_provider and selected_provider != "local" else None
        provider = LLMProvider(
            provider=provider_name,
            model=context.get("llm_model") or None,
        )
        log_event(
            logger,
            20,
            "story_provider_selected",
            session_id=session_id,
            job_id=job_id,
            provider=provider.provider,
            model=provider.model,
            configured=provider.configured,
            media_item_count=len(media_items),
            stage="story_generation",
        )
        if provider.configured:
            _job_progress(job_id, session_id, "planning", f"Calling {provider.provider} LLM for voiceover and smart edit decisions", 45)
        else:
            _job_progress(job_id, session_id, "planning", f"Using local fallback because {provider.provider} is not configured", 45)
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
        if job_id:
            _update_job(job_id, state="complete", current_step="Narrative plan generated", progress_percent=100, error=None)
        log_event(
            logger,
            20,
            "story_job_complete",
            session_id=session_id,
            job_id=job_id,
            provider=provider.provider,
            model=provider.model,
            llm_used=generation.get("llm_used"),
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="success",
            stage="story_generation",
        )
    except Exception as exc:
        logger.exception("Story planning failed")
        log_event(
            logger,
            40,
            "story_job_failed",
            session_id=session_id,
            job_id=job_id,
            exception_type=type(exc).__name__,
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="hard_failure",
            stage="story_generation",
        )
        if job_id:
            _update_job(job_id, state="failed", current_step="Story planning failed", error=str(exc))
        _update_session(
            session_id,
            phase="error",
            progress_label="Story planning failed",
            next_action="Adjust the context or upload media, then try again.",
            error=str(exc),
        )


def _render_background(session_id: str, job_id: str | None = None) -> None:
    started = time.monotonic()
    try:
        log_event(logger, 20, "render_job_start", session_id=session_id, job_id=job_id, stage="render")
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
        timeline_decisions = story_plan.get("edit_decisions") or []
        log_event(
            logger,
            20,
            "render_job_inputs",
            session_id=session_id,
            job_id=job_id,
            clip_count=len(clips),
            selected_timeline_clip_count=len(timeline_decisions) or len(clips),
            include_title_card=render_options.get("include_title_card", True),
            aspect_ratio=render_options.get("aspect_ratio", "original"),
            stage="render",
        )

        _update_session(
            session_id,
            phase="rendering",
            progress_label="Rendering holiday recap",
            next_action="I am stitching the clips, generating narration when TTS is configured, and mixing the final audio.",
            progress_percent=10,
            error=None,
        )
        _job_progress(job_id, session_id, "preparing", "Preparing story-aware render", 15)

        def progress_callback(state: str, progress_percent: int) -> None:
            labels = {
                "rendering_segments": "Rendering timeline segments",
                "writing_captions": "Writing captions and edit decisions",
                "synthesizing_narration": "Synthesizing narration",
                "mixing_audio": "Mixing narration with video",
            }
            _job_progress(job_id, session_id, state, labels.get(state, state.replace("_", " ")), progress_percent)

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
            progress_callback=progress_callback,
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
        if job_id:
            _update_job(job_id, state="complete", current_step="Render complete", progress_percent=100, error=None)
        log_event(
            logger,
            20,
            "render_job_complete",
            session_id=session_id,
            job_id=job_id,
            output_path=Path(rendered_path).name,
            narration_written=narration_path.exists(),
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="success",
            stage="render",
        )
    except Exception as exc:
        logger.exception("Render failed")
        log_event(
            logger,
            40,
            "render_job_failed",
            session_id=session_id,
            job_id=job_id,
            exception_type=type(exc).__name__,
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="hard_failure",
            stage="render",
        )
        if job_id:
            _update_job(job_id, state="failed", current_step="Render failed", error=str(exc))
        _update_session(
            session_id,
            phase="error",
            progress_label="Render failed",
            next_action="Check the uploaded files and try rendering again.",
            error=str(exc),
        )


def run_queued_job(job_id: str) -> None:
    job = _get_job(job_id)
    _update_job(job_id, attempts=int(job.get("attempts") or 0) + 1)
    log_event(logger, 20, "job_run_start", session_id=job["session_id"], job_id=job_id, job_type=job["type"], attempt=int(job.get("attempts") or 0) + 1)
    if job["type"] == "story_generation":
        _generate_story_background(job["session_id"], job_id=job_id)
        return
    if job["type"] == "render":
        _render_background(job["session_id"], job_id=job_id)
        return
    _update_job(job_id, state="failed", current_step="Unknown job type", error=f"Unsupported job type: {job['type']}")
    log_event(logger, 40, "job_run_failed", session_id=job["session_id"], job_id=job_id, job_type=job["type"], outcome="unsupported_job_type")
    raise ValueError(f"Unsupported job type: {job['type']}")


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
    sessions.sort(key=lambda item: _timestamp(item.get("updated_at"), 0), reverse=True)
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
    auth: dict[str, str] = Depends(_auth_context),
) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    if not session.get("media_items"):
        raise HTTPException(status_code=409, detail="Upload media before generating the story.")
    _update_session(
        session_id,
        phase="planning",
        progress_label="Queued story generation",
        next_action="The story job is queued for the worker.",
        progress_percent=0,
        error=None,
    )
    _enqueue_job(session_id, "story_generation")
    return _public_session(session_id)


@app.post("/sessions/{session_id}/render")
def render_session(
    session_id: str,
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
    _update_session(
        session_id,
        phase="rendering",
        progress_label="Queued render",
        next_action="The render job is queued for the worker.",
        progress_percent=0,
        error=None,
    )
    _enqueue_job(session_id, "render")
    return _public_session(session_id)


@app.get("/sessions/{session_id}/jobs/{job_id}")
def get_job(session_id: str, job_id: str, auth: dict[str, str] = Depends(_auth_context)) -> dict[str, Any]:
    session = _public_session(session_id)
    _ensure_owner(session, _owner_from_auth(auth))
    job = _get_job(job_id)
    if job["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
            with _connect_db() as conn:
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                conn.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
                conn.commit()
    shutil.rmtree(MEDIA_ROOT / session_id, ignore_errors=True)
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("TRIPSTORY_API_PORT", "8010")))

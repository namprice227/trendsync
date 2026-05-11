from __future__ import annotations

import base64
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

MEDIA_ROOT = Path(os.environ.get("TRENDFLOW_MOBILE_DIR", "mobile_sessions"))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

PHASE_SCREENS = {
    "awaiting_reference": "analyze",
    "analyzing": "analyze",
    "ready_to_film": "studio",
    "needs_adjustment": "studio",
    "ready_to_record": "studio",
    "uploading": "studio",
    "rendering_ready": "output",
    "rendering": "output",
    "evaluating": "output",
    "complete": "output",
    "error": "analyze",
}

app = FastAPI(
    title="TrendFlow Mobile API",
    description="Session-state API for the Expo mobile director app.",
    version="0.1.0",
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
_runtime: dict[str, dict[str, Any]] = {}


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=6)


class PreflightFrameRequest(BaseModel):
    image_base64: str = Field(..., min_length=40)


def _now() -> float:
    return round(time.time(), 3)


def _session_dir(session_id: str) -> Path:
    path = MEDIA_ROOT / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _create_session() -> dict[str, Any]:
    session_id = uuid.uuid4().hex[:12]
    session = {
        "id": session_id,
        "phase": "awaiting_reference",
        "screen": "analyze",
        "next_action": "Paste a TikTok or Reel URL. I will move you into the studio when analysis is ready.",
        "created_at": _now(),
        "updated_at": _now(),
        "error": None,
        "progress_label": "Waiting for reference",
        "style": None,
        "context_summary": None,
        "script": None,
        "skill_dir": None,
        "required_shots": 0,
        "current_shot_idx": 0,
        "current_shot_duration": 3.0,
        "recorded_clips": [],
        "feedback": [],
        "director_feedback": "",
        "final_video_url": None,
        "evaluation": None,
    }
    with _lock:
        _sessions[session_id] = session
        _runtime[session_id] = {"prev_gray": None, "reference_poses": [], "pose_tracker": None, "context": None}
    _session_dir(session_id)
    return _public_session(session_id)


def _public_session(session_id: str) -> dict[str, Any]:
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        public = dict(session)
        public["screen"] = PHASE_SCREENS.get(public["phase"], "analyze")
        return public


def _update_session(session_id: str, **updates: Any) -> dict[str, Any]:
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        session.update(updates)
        session["screen"] = PHASE_SCREENS.get(session["phase"], "analyze")
        session["updated_at"] = _now()
        return dict(session)


def _runtime_for(session_id: str) -> dict[str, Any]:
    with _lock:
        if session_id not in _runtime:
            raise HTTPException(status_code=404, detail="Session not found")
        return _runtime[session_id]


def _shot_duration(session_id: str, shot_idx: int) -> float:
    context = _runtime_for(session_id).get("context") or {}
    cuts = context.get("cuts") or []
    if shot_idx < len(cuts) - 1:
        return max(0.5, float(cuts[shot_idx + 1]) - float(cuts[shot_idx]))
    return 3.0


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    cuts = context.get("cuts") or []
    beats = context.get("beats") or []
    beat_cut_sync = context.get("beat_cut_sync") or []
    synced = sum(1 for item in beat_cut_sync if item.get("synced"))
    motion_counts: dict[str, int] = {}
    for entry in context.get("camera_motion") or []:
        motion = entry.get("motion", "static")
        motion_counts[motion] = motion_counts.get(motion, 0) + 1
    return {
        "bpm": context.get("bpm"),
        "shots": len(cuts) - 1 if len(cuts) > 1 else 1,
        "duration": cuts[-1] if cuts else None,
        "beats": len(beats),
        "beat_synced_cuts": synced,
        "total_cuts": len(beat_cut_sync),
        "camera_motion": motion_counts,
    }


def _decode_frame(image_base64: str):
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 image") from exc
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image frame")
    return frame


def _safe_name(name: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name)
    return cleaned or fallback


def _analyze_background(session_id: str, url: str) -> None:
    try:
        from analyzer import analyze_trend
        from director import PoseTracker
        from scriptwriter import generate_script
        from skill_manager import load_reference_poses

        _update_session(
            session_id,
            phase="analyzing",
            progress_label="Analyzing reference",
            next_action="Reading the trend, cuts, beats, camera motion, pose data, and style.",
            error=None,
        )
        ref_dir = _session_dir(session_id) / "reference"
        trend_name = f"mobile_{session_id}"
        skill_dir, style, context = analyze_trend(url, output_dir=str(ref_dir), trend_name=trend_name)
        script = generate_script(style)
        reference_poses = load_reference_poses(trend_name)
        pose_tracker = PoseTracker()
        required_shots = len(context.get("cuts") or []) - 1
        if required_shots < 1:
            required_shots = 1
        with _lock:
            _runtime[session_id].update(
                {
                    "context": context,
                    "reference_poses": reference_poses,
                    "pose_tracker": pose_tracker,
                    "prev_gray": None,
                }
            )
        _update_session(
            session_id,
            phase="ready_to_film",
            progress_label="Studio ready",
            next_action="Camera guidance will start automatically. When the frame matches, I will start recording.",
            style=style,
            context_summary=_context_summary(context),
            script=script,
            skill_dir=skill_dir,
            required_shots=required_shots,
            current_shot_idx=0,
            current_shot_duration=_shot_duration(session_id, 0),
            feedback=[],
            director_feedback="",
        )
    except Exception as exc:
        _update_session(
            session_id,
            phase="error",
            progress_label="Analysis failed",
            next_action="Check the URL and try analysis again.",
            error=str(exc),
        )


def _render_and_evaluate_background(session_id: str) -> None:
    try:
        from evaluator import evaluate_final_video
        from renderer import render_final_video
        from skill_manager import load_skill

        session = _public_session(session_id)
        clips = list(session["recorded_clips"])
        if not clips:
            raise ValueError("No clips available to render.")
        skill_dir = session.get("skill_dir")
        if not skill_dir:
            raise ValueError("No analyzed skill is attached to this session.")

        output_path = _session_dir(session_id) / "final_trend.mp4"
        _update_session(
            session_id,
            phase="rendering",
            progress_label="Assembling final video",
            next_action="I am syncing the footage to the reference beats.",
        )
        rendered_path = render_final_video(clips, skill_dir, output_path=str(output_path))
        final_url = f"/files/{session_id}/{Path(rendered_path).name}"
        _update_session(
            session_id,
            phase="evaluating",
            progress_label="Judging final cut",
            next_action="The AI judge is scoring the rendered video.",
            final_video_url=final_url,
        )

        style_profile = None
        try:
            trend_name = os.path.basename(skill_dir)
            style_profile, _, _ = load_skill(trend_name)
        except Exception:
            style_profile = session.get("style")
        evaluation = evaluate_final_video(rendered_path, style_profile)
        if not isinstance(evaluation, str):
            evaluation = str(evaluation)
        _update_session(
            session_id,
            phase="complete",
            progress_label="Final video ready",
            next_action="Review the output and score. Start a new session when you want another trend.",
            final_video_url=final_url,
            evaluation=evaluation,
        )
    except Exception as exc:
        _update_session(
            session_id,
            phase="error",
            progress_label="Render failed",
            next_action="Upload the clip again or start a new session.",
            error=str(exc),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions")
def create_session() -> dict[str, Any]:
    return _create_session()


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    return _public_session(session_id)


@app.post("/sessions/{session_id}/analyze")
def analyze_session(session_id: str, request: AnalyzeRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    _public_session(session_id)
    _update_session(
        session_id,
        phase="analyzing",
        progress_label="Queued analysis",
        next_action="Keep the phone nearby. I will open Studio when the reference is ready.",
        error=None,
    )
    background_tasks.add_task(_analyze_background, session_id, request.url)
    return _public_session(session_id)


@app.post("/sessions/{session_id}/preflight-frame")
def preflight_frame(session_id: str, request: PreflightFrameRequest) -> dict[str, Any]:
    from director import encode_image_base64, get_fast_feedback, get_vlm_feedback
    from skill_manager import load_skill

    session = _public_session(session_id)
    if session["phase"] in {"ready_to_record", "uploading", "rendering", "evaluating", "complete"}:
        return session
    if session["phase"] not in {"ready_to_film", "needs_adjustment"}:
        raise HTTPException(status_code=409, detail=f"Pre-flight is not available during phase {session['phase']}")

    frame_bgr = _decode_frame(request.image_base64)
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())

    runtime = _runtime_for(session_id)
    current_time = sum(_shot_duration(session_id, idx) for idx in range(session["current_shot_idx"]))
    fast_feedback, prev_gray = get_fast_feedback(
        frame_rgb,
        runtime.get("pose_tracker"),
        runtime.get("reference_poses") or [],
        (runtime.get("context") or {}).get("camera_motion") or [],
        current_time,
        runtime.get("prev_gray"),
    )
    runtime["prev_gray"] = prev_gray

    checks: list[str] = []
    blockers: list[str] = []
    if brightness < 60:
        blockers.append("Lighting is too dark.")
        checks.append("Lighting: too dark")
    elif brightness > 220:
        blockers.append("Lighting is overexposed.")
        checks.append("Lighting: too bright")
    else:
        checks.append("Lighting: good")

    if fast_feedback and fast_feedback != "Analyzing...":
        checks.append(fast_feedback)

    system_prompt = None
    skill_dir = session.get("skill_dir")
    if skill_dir:
        try:
            trend_name = os.path.basename(skill_dir)
            _, markdown_body, context = load_skill(trend_name)
            scene_prompts = context.get("scene_prompts") or []
            shot_idx = session["current_shot_idx"]
            system_prompt = scene_prompts[shot_idx] if shot_idx < len(scene_prompts) else markdown_body
        except Exception:
            system_prompt = None

    cv_context = " | ".join(checks) if checks else None
    director_feedback = get_vlm_feedback(encode_image_base64(frame_bgr), system_prompt=system_prompt, cv_context=cv_context)
    is_perfect = director_feedback.strip().lower() == "perfect" or "perfect" in director_feedback.lower()
    is_ready = is_perfect and not blockers

    shot_idx = session["current_shot_idx"]
    duration = _shot_duration(session_id, shot_idx)
    if is_ready:
        return _update_session(
            session_id,
            phase="ready_to_record",
            progress_label=f"Shot {shot_idx + 1} locked",
            next_action="Hold still. Recording starts automatically.",
            current_shot_duration=duration,
            feedback=checks,
            director_feedback=director_feedback,
        )

    if not blockers and director_feedback:
        blockers.append(director_feedback)
    return _update_session(
        session_id,
        phase="needs_adjustment",
        progress_label=f"Adjust shot {shot_idx + 1}",
        next_action="Make the suggested adjustment. I will keep checking the camera automatically.",
        current_shot_duration=duration,
        feedback=checks + blockers,
        director_feedback=director_feedback,
    )


@app.post("/sessions/{session_id}/clips")
async def upload_clips(
    session_id: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    auto_render: bool = Query(default=True),
    full_take: bool = Query(default=False),
) -> dict[str, Any]:
    session = _public_session(session_id)
    if not session.get("skill_dir"):
        raise HTTPException(status_code=409, detail="Analyze a reference before uploading clips.")
    if not files:
        raise HTTPException(status_code=400, detail="No clips uploaded.")

    _update_session(
        session_id,
        phase="uploading",
        progress_label="Receiving footage",
        next_action="I am saving the clip and deciding the next step.",
    )

    clips_dir = _session_dir(session_id) / "recorded_shots"
    clips_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = list(session.get("recorded_clips") or [])
    start_idx = len(saved_paths)
    for offset, upload in enumerate(files):
        suffix = Path(upload.filename or "").suffix or ".mp4"
        filename = _safe_name(upload.filename or f"shot_{start_idx + offset}{suffix}", f"shot_{start_idx + offset}{suffix}")
        target = clips_dir / f"{start_idx + offset:02d}_{filename}"
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        saved_paths.append(str(target))

    required = session["required_shots"] or 1
    if full_take or len(saved_paths) >= required:
        _update_session(
            session_id,
            phase="rendering_ready",
            progress_label="Footage ready",
            next_action="I will assemble and judge the final video now.",
            recorded_clips=saved_paths,
            current_shot_idx=min(len(saved_paths), required),
        )
        if auto_render:
            background_tasks.add_task(_render_and_evaluate_background, session_id)
    else:
        next_idx = len(saved_paths)
        _runtime_for(session_id)["prev_gray"] = None
        _update_session(
            session_id,
            phase="ready_to_film",
            progress_label=f"Shot {next_idx + 1} ready",
            next_action="Line up the next shot. I will run pre-flight automatically.",
            recorded_clips=saved_paths,
            current_shot_idx=next_idx,
            current_shot_duration=_shot_duration(session_id, next_idx),
            feedback=[],
            director_feedback="",
        )
    return _public_session(session_id)


@app.post("/sessions/{session_id}/render")
def render_session(session_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    session = _public_session(session_id)
    if not session.get("recorded_clips"):
        raise HTTPException(status_code=409, detail="Upload footage before rendering.")
    background_tasks.add_task(_render_and_evaluate_background, session_id)
    return _update_session(
        session_id,
        phase="rendering",
        progress_label="Assembling final video",
        next_action="I am syncing the footage to the trend.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("TRENDFLOW_API_PORT", "8010")))

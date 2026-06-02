# TripStory API Specification

This document defines the REST API surface for the TripStory backend (`api_server.py`). It follows an asynchronous, job-based architecture to handle long-running media processing tasks without blocking the client.

## Base URL
`/api/v1`

---

## 1. Session Management

### `POST /sessions`
Creates a new project session.
- **Request:** Empty body.
- **Response:**
  ```json
  {
    "session_id": "uuid",
    "status": "created",
    "created_at": "timestamp"
  }
  ```

### `GET /sessions/{session_id}`
Retrieves the current state of a session, including job progress. This is the primary polling endpoint for the frontend UI.
- **Response:**
  ```json
  {
    "session_id": "uuid",
    "phase": "uploading | analyzing | planning | rendering | complete | error",
    "progress_percent": 45,
    "active_job_state": "queued | started | finished | failed",
    "active_job_step": "detecting_scenes",
    "error": null,
    "context": { ... },
    "story_plan": { ... }
  }
  ```

### `PATCH /sessions/{session_id}/context`
Updates user-provided trip context.
- **Request Body:** Match `User Trip Context` schema in `SCHEMA.md`.

---

## 2. Media Upload

### `POST /sessions/{session_id}/media`
Uploads a raw video clip to the session.
- **Content-Type:** `multipart/form-data`
- **Payload:** `file` (binary video file)
- **Response:**
  ```json
  {
    "clip_id": "uuid",
    "filename": "string",
    "status": "uploaded"
  }
  ```
*(Note: Uploading triggers background intelligence extraction jobs. Clients should poll `/sessions/{session_id}` to track analysis progress).*

---

## 3. Story Generation

### `POST /sessions/{session_id}/generate_story`
Triggers the Story Planner LLM to generate the `story_plan` based on uploaded media and context.
- **Request:**
  ```json
  {
    "target_duration_seconds": 60.0,
    "language": "en"
  }
  ```
- **Response:** `202 Accepted` (Job enqueued)

### `PATCH /sessions/{session_id}/voiceover_segments`
Allows the user to manually edit the generated script before rendering.
- **Request:** List of modified `voiceover_segments`.
- **Response:** `200 OK`

---

## 4. Render & Export

### `POST /sessions/{session_id}/render`
Triggers the final assembly (FFmpeg cutting, TTS generation, audio mixing).
- **Request:** Empty body (uses the saved `story_plan`).
- **Response:** `202 Accepted` (Job enqueued)

### `GET /sessions/{session_id}/export`
Returns the URL to download the final rendered `.mp4` rough cut.
- **Response:**
  ```json
  {
    "download_url": "/static/sessions/{session_id}/holiday_recap.mp4"
  }
  ```

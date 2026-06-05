# TripStory API Specification

This document describes the current FastAPI surface implemented in `api_server.py`.
Routes are mounted at the API root, not under `/api/v1`.

## Auth And Ownership

Local development works without auth. When `TRIPSTORY_AUTH_TOKEN` is set, requests must include either:

```text
Authorization: Bearer <token>
```

or:

```text
X-TripStory-Token: <token>
```

Project ownership is derived from `X-TripStory-User` or `x-tripstory-owner` in local mode. In Cloudflare Access mode, ownership can come from `Cf-Access-Authenticated-User-Email` when the corresponding environment flags are enabled.

## Health

### `GET /health`

Returns:

```json
{"status":"ok","product":"TripStory"}
```

### `HEAD /health`

Returns HTTP 200.

## Sessions And Projects

### `GET /sessions`

Lists projects for the authenticated owner.

Returns:

```json
{
  "sessions": [
    {
      "id": "session-id",
      "title": "Trip title",
      "destination": "Kyoto",
      "phase": "ready_to_render",
      "updated_at": 1710000000.0,
      "media_count": 3,
      "final_video_url": "/files/session-id/holiday_recap.mp4",
      "share_token": "optional-token"
    }
  ]
}
```

### `POST /sessions`

Creates a new project session.

Returns the full public session object.

### `GET /sessions/{session_id}`

Returns the full public session object, including:

- `phase`
- `screen`
- `progress_percent`
- `trip_context`
- `media_items`
- `scene_memories`
- `scene_memory_url`
- `creative_brief`
- `story_plan`
- render artifact URLs
- `active_job`, when a story or render job is queued/running

### `PATCH /sessions/{session_id}/metadata`

Updates project metadata.

Request:

```json
{"title":"Spring family edit"}
```

Returns the full public session object.

### `POST /sessions/{session_id}/duplicate`

Copies a project, including media files, story plan, render options, and render artifacts. The share token is not copied.

Returns the duplicated session.

### `DELETE /sessions/{session_id}`

Deletes the project, its jobs, and its media directory.

Returns:

```json
{"status":"deleted"}
```

## Trip Context

### `POST /sessions/{session_id}/context`

Saves user-provided trip context. API keys are never accepted from the frontend.

Request:

```json
{
  "destination": "Kyoto",
  "duration": "5 days",
  "places_visited": "Gion, Arashiyama",
  "travel_dates": "April 2026",
  "companions": "family",
  "highlights": "sunset by the river",
  "mood": "warm and reflective",
  "audience": "friends and family",
  "language": "en",
  "notes": "",
  "llm_provider": "deepseek",
  "llm_model": ""
}
```

Returns the full public session object.

## Media Upload

### `POST /sessions/{session_id}/media`

Uploads one or more video files.

Content type: `multipart/form-data`

Field name: `files`

Allowed suffixes:

- `.mp4`
- `.mov`
- `.m4v`
- `.webm`

The current MVP analyzes clips synchronously during the upload request with bounded ffmpeg/OpenCV work. It also writes `scene_memory.json` for the project. Story generation and rendering are queued separately through Redis/RQ.

Returns the updated public session object with `media_items`, `clip_analysis`, `scene_memories`, and `scene_memory_url`.

## Creative Brief

### `POST /sessions/{session_id}/creative-brief`

Drafts a producer brief from uploaded media and trip context.

Returns the updated public session object.

### `PATCH /sessions/{session_id}/creative-brief`

Updates the selected direction, question answers, or notes.

Request:

```json
{
  "selected_direction_id": "direction_1",
  "answers": [
    {"question_id": "audience_intent", "answer": "For close friends."}
  ],
  "notes": "Keep it personal."
}
```

Returns the updated public session object.

### `POST /sessions/{session_id}/creative-brief/approve`

Approves the current creative brief. Story generation is blocked while a draft brief exists and is not approved.

Returns the updated public session object.

## Story Generation

### `POST /sessions/{session_id}/generate-story`

Queues story generation through Redis/RQ when `TRIPSTORY_QUEUE_BACKEND=rq`.

Request body is optional. When present, it accepts the same render/regeneration options as `/render`:

```json
{
  "aspect_ratio": "original",
  "target_duration_seconds": 60,
  "clip_order": ["clip_001", "clip_002"],
  "favorite_clip_ids": ["clip_001"],
  "excluded_clip_ids": ["clip_003"],
  "pinned_scene_ids": ["clip_001_scene_001"],
  "excluded_scene_ids": ["clip_003_scene_001"],
  "burn_captions": false,
  "include_title_card": true,
  "include_music_bed": false
}
```

Story generation uses `scene_memories` as the primary planning evidence, filters out excluded clips/scenes before calling the planner, and passes pinned/excluded IDs as explicit constraints.

Returns the updated public session object with `phase="planning"` and an `active_job`.

## Voiceover Review

### `PATCH /sessions/{session_id}/voiceover-segments`

Edits generated voiceover text and captions by `segment_id`.

Request:

```json
{
  "segments": [
    {
      "segment_id": "seg_001",
      "voiceover": "Kyoto starts with lanterns glowing over the narrow street.",
      "caption": "Lantern street"
    }
  ]
}
```

If an existing render is present, editing voiceover clears stale render artifact URLs and returns the session to `ready_to_render`.

## Timeline Review

### `PATCH /sessions/{session_id}/timeline`

Edits the generated timeline by `segment_id`. This supports source-window nudging, per-segment duration changes, and generated segment reordering after story planning.

Request:

```json
{
  "segment_order": ["seg_002", "seg_001"],
  "segments": [
    {
      "segment_id": "seg_001",
      "start_time": 1.5,
      "duration": 3
    },
    {
      "segment_id": "seg_002",
      "start_time": 4,
      "duration": 2.5
    }
  ]
}
```

Rules:

- `segment_order`, when supplied, must include every generated timeline segment exactly once.
- `duration` must be between 1 and 10 seconds.
- Editing while story planning or rendering is in progress returns HTTP 409.
- If an existing render is present, timeline editing clears stale render artifact URLs and returns the session to `ready_to_render`.

## Render

### `POST /sessions/{session_id}/render`

Queues final video rendering through Redis/RQ when `TRIPSTORY_QUEUE_BACKEND=rq`.

Request body is optional. When present, it accepts:

```json
{
  "aspect_ratio": "original",
  "target_duration_seconds": 30,
  "clip_order": [],
  "favorite_clip_ids": [],
  "excluded_clip_ids": [],
  "pinned_scene_ids": [],
  "excluded_scene_ids": [],
  "burn_captions": false,
  "include_title_card": true,
  "include_music_bed": false
}
```

Returns the updated public session object with `phase="rendering"` and an `active_job`.

## Jobs

### `GET /sessions/{session_id}/jobs/{job_id}`

Returns a job row for the session.

Job states include:

- `queued`
- `analyzing`
- `planning`
- `preparing`
- `rendering_segments`
- `writing_captions`
- `synthesizing_narration`
- `mixing_audio`
- `complete`
- `failed`

## Sharing

### `POST /sessions/{session_id}/share`

Creates or reuses a share token.

Returns:

```json
{
  "share_token": "token",
  "share_url": "https://api.example.com/share/token",
  "session": {}
}
```

### `GET /share/{share_token}`

Returns the shared public session.

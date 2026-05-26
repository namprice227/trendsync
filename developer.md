# TripStory Developer Guide

This document explains how the current TripStory workflow works, where each piece lives, and what to improve next.

## Product Goal

TripStory turns uploaded trip videos into a short social recap:

1. User enters trip context.
2. User uploads raw video clips.
3. Backend analyzes clips.
4. Gemini vision summarizes sampled video frames.
5. DeepSeek writes the story plan, edit decisions, and voiceover segments.
6. Renderer trims clips, orders them, writes captions, optionally generates narration, and exports the final video.
7. Expo web/mobile app displays the plan and final output.

The intended split is:

- DeepSeek: text reasoning, story planning, voiceover writing, edit decision planning.
- Gemini: sampled-frame visual understanding.
- OpenAI: optional speech transcription and optional text-to-speech narration.
- Local fallback: still produces a usable plan when no LLM is configured.

## Main Files

- `api_server.py`: FastAPI API, sessions, upload, planning, rendering, auth, persistence.
- `llm_provider.py`: provider abstraction for OpenAI-compatible chat APIs, including DeepSeek/Gemini/OpenAI.
- `media_intelligence.py`: video probing, OpenCV frame sampling, audio metrics, optional transcription, Gemini/OpenAI frame vision.
- `trip_story.py`: prompt contract, fallback story generation, LLM response normalization, voiceover cleanup.
- `trip_renderer.py`: ffmpeg timeline assembly, trimming, title card, captions, narration mixing.
- `tts_provider.py`: OpenAI TTS client and ffmpeg audio mixing helper.
- `mobile/App.tsx`: Expo app UI and workflow screens.
- `mobile/src/api.ts`: frontend API client.
- `mobile/src/types.ts`: frontend TypeScript shapes.
- `tests/test_tripstory_api.py`: backend regression tests.
- `.env.example`: safe config template.

## Environment

Use `.env` for local secrets. It is ignored by git.

Recommended AI setup:

```bash
TRIPSTORY_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-real-deepseek-key
TRIPSTORY_DEEPSEEK_MODEL=deepseek-v4-pro
TRIPSTORY_DEEPSEEK_THINKING=enabled
TRIPSTORY_DEEPSEEK_REASONING_EFFORT=high

GEMINI_API_KEY=your-real-gemini-key
TRIPSTORY_VISION_PROVIDER=gemini
TRIPSTORY_GEMINI_VISION_MODEL=gemini-2.0-flash
TRIPSTORY_ENABLE_VISION_ANALYSIS=1
```

Optional narration:

```bash
OPENAI_API_KEY=your-openai-key
TRIPSTORY_TTS_PROVIDER=openai
TRIPSTORY_TTS_MODEL=gpt-4o-mini-tts
TRIPSTORY_TTS_VOICE=coral
```

Rate limiting knobs:

```bash
TRIPSTORY_LLM_MIN_INTERVAL_SECONDS=3
TRIPSTORY_LLM_MAX_RETRIES=2
TRIPSTORY_VISION_MIN_INTERVAL_SECONDS=3
TRIPSTORY_VISION_MAX_RETRIES=2
TRIPSTORY_TTS_MIN_INTERVAL_SECONDS=3
TRIPSTORY_TTS_MAX_RETRIES=2
```

Storage:

```bash
TRIPSTORY_MEDIA_DIR=trip_sessions
TRIPSTORY_SESSION_STORE=trip_sessions_sessions.json
TRIPSTORY_SESSION_DB=trip_sessions.sqlite3
TRIPSTORY_MAX_UPLOAD_MB=512
```

## End-To-End Flow

### 1. Session Creation

The frontend calls the session endpoint in `api_server.py`.

The backend creates a default session with:

- `phase=collecting_context`
- `screen=context`
- default trip context
- empty `media_items`
- empty `clip_analysis`
- default render options
- default provider `deepseek`

Sessions are kept in memory and persisted to both:

- JSON backup: `trip_sessions_sessions.json`
- SQLite: `trip_sessions.sqlite3`

The SQLite table stores the whole session object as JSON. This is simple and flexible, but not ideal for production querying.

### 2. Trip Context

The app saves context fields:

- destination
- duration
- places visited
- dates
- companions
- highlights
- mood
- audience
- language
- notes
- LLM provider/model override

Important: API keys are never accepted from the frontend. Keys only come from server environment variables.

### 3. Upload

Upload is handled in `api_server.py`.

Allowed video suffixes:

- `.mp4`
- `.mov`
- `.m4v`
- `.webm`

For every uploaded video:

1. File is saved under `trip_sessions/<session_id>/media/`.
2. Size and type are checked.
3. `analyze_clip()` in `media_intelligence.py` runs.
4. Analysis is stored on the media item and copied into `clip_analysis`.

### 4. Clip Intelligence

`media_intelligence.py` produces two kinds of intelligence.

Local deterministic analysis:

- duration
- width and height
- fps
- bitrate
- audio stream present
- mean/max audio levels through ffmpeg
- brightness
- sharpness
- simple motion score
- scene timestamps
- best moment timestamps
- landmark candidate timestamps
- face hits through OpenCV Haar cascade
- quality label

Optional external analysis:

- OpenAI audio transcription when `TRIPSTORY_ENABLE_TRANSCRIPTION=1`.
- Gemini frame vision when `TRIPSTORY_ENABLE_VISION_ANALYSIS=1` and `GEMINI_API_KEY` is present.

Gemini vision workflow:

1. Pick timestamps from best moments, landmark candidates, or scene changes.
2. Extract up to `TRIPSTORY_VISION_MAX_FRAMES` frames.
3. Resize and JPEG-compress frames.
4. Send data URLs to Gemini through the OpenAI-compatible `/chat/completions` endpoint.
5. Ask for strict JSON:
   - `summary`
   - `visible_subjects`
   - `locations_or_scenes`
   - `actions`
   - `mood`
   - `avoid_reasons`
   - `best_moment_descriptions`

If vision fails, the backend falls back to heuristic summaries. The app should still work, but story quality is weaker.

### 5. Story Planning

Story planning is in `trip_story.py`.

The backend builds a `media_summary` from uploaded items and sends it to `LLMProvider`.

The LLM is asked to return strict JSON:

- `title`
- `language`
- `tone`
- `narrative_arc`
- `voiceover_script`
- `voiceover_segments`
- `edit_notes`
- `clip_plan`
- `edit_decisions`

`edit_decisions` are the editor-facing timeline. Each item should include:

- `clip_id`
- `clip`
- `start_time`
- `duration`
- `role`
- `reason`
- `transition`
- `caption`
- `audio_strategy`

`voiceover_segments` are audience-facing narration. They must align with `edit_decisions`. Each item should include:

- `clip_id`
- `clip`
- `start_time`
- `duration`
- `voiceover`
- `caption`
- `purpose`

The backend normalizes malformed model output. If the model returns strings where arrays are expected, or wrong types for durations, the normalizer repairs those into stable shapes.

### 6. Voiceover Cleanup

The app previously produced technical voiceover like:

```text
25.19s, 1280x720, 1 scenes, strong quality, 9 face hits, audio present
```

That is now blocked in `trip_story.py`.

Technical metadata can be used in `reason` fields for edit decisions, but it must not appear in:

- `voiceover_script`
- `voiceover_segments[*].voiceover`
- captions

The cleanup detects:

- seconds like `25.19s`
- resolution like `1280x720`
- scene counts
- face hit counts
- quality labels
- `audio present`
- generic phrases like `this moment shows`

If detected, it rewrites the line into a TikTok-style narration cue based on destination, highlights, visible subjects, scenes, actions, and fallback social phrasing.

Example fallback:

```text
POV: Tromso, Norway gives you the kind of memory you want to replay: the smiles and reactions that make the trip feel alive.
```

### 7. LLM Provider

`llm_provider.py` is a small OpenAI-compatible chat client.

Provider presets:

- OpenAI: `https://api.openai.com/v1`
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai`
- DeepSeek: `https://api.deepseek.com`

Endpoint handling:

- If base URL does not end with `/chat/completions`, the client appends it.
- DeepSeek therefore posts to `https://api.deepseek.com/chat/completions`.

DeepSeek-specific payload fields:

```json
{
  "thinking": { "type": "enabled" },
  "reasoning_effort": "high"
}
```

These are controlled by:

```bash
TRIPSTORY_DEEPSEEK_THINKING=enabled
TRIPSTORY_DEEPSEEK_REASONING_EFFORT=high
```

The chat client serializes calls with a lock and sleeps between requests to reduce 429s.

### 8. Render

Rendering is in `trip_renderer.py`.

The renderer:

1. Builds a smart timeline from `story_plan.edit_decisions`.
2. Falls back to best detected moments if no edit decisions exist.
3. Optionally creates a title card.
4. Trims each source clip using ffmpeg.
5. Applies aspect ratio formatting.
6. Adds basic fade in/out on segments.
7. Concatenates segments.
8. Writes `edit_decisions.json`.
9. Writes SRT/VTT captions from timeline-aligned voiceover segments.
10. Synthesizes narration if TTS is configured.
11. Mixes narration under original audio.
12. Saves `story_plan.json`.

Current render outputs are stored under:

```text
trip_sessions/<session_id>/
```

Common output files:

- `holiday_recap.mp4`
- `holiday_recap_assembly.mp4`
- `voiceover.mp3`
- `captions.srt`
- `captions.vtt`
- `story_plan.json`
- `edit_decisions.json`

### 9. Frontend

The Expo app in `mobile/App.tsx` has four main screens:

- Context
- Upload/media
- Plan
- Output

The UI shows:

- API connection field
- project library
- trip context form
- language and provider picker
- upload action
- clip intelligence
- story brain/provider status
- generated voiceover
- narrative arc
- smart edit decisions
- timeline/export controls
- rendered video preview

The frontend never sees provider API keys.

## How To Run

Backend:

```bash
.conda/trendsync-py312/bin/python -m uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Frontend:

```bash
cd mobile
npm run web -- --clear --port 8081
```

Tests:

```bash
.conda/trendsync-py312/bin/python -m unittest discover -s tests
cd mobile
npm run typecheck
```

## Current Strengths

- Server-side API keys only.
- DeepSeek/Gemini provider split.
- Gemini frame summaries feed DeepSeek story planning.
- Fallback path works without external LLM.
- LLM output normalization prevents many blank-page crashes.
- Voiceover metadata cleanup prevents technical narration.
- Timeline-aligned voiceover segments and captions.
- Render follows planned clip order/start/duration.
- Session persistence survives API restart.

## Current Limitations

- Background work uses FastAPI background tasks, not a durable queue.
- SQLite stores full session JSON, not normalized relational tables.
- Vision only samples a few frames per clip.
- Scene detection is simple histogram comparison.
- Face detection is basic Haar cascade, not modern face recognition.
- No dedicated landmark classifier.
- TTS is OpenAI-only.
- No music library or beat-sync editing.
- No waveform view or visual timeline editor.
- Render transitions are simple fades, not full nonlinear editing.
- Long uploads are not resumable.
- The mobile app is Expo web/mobile, not a polished native editor yet.

## Good Next Improvements

### Better Clip Intelligence

- Extract thumbnails and show them in the UI.
- Sample one frame per scene, not only top-scored frames.
- Add shot boundary detection with a stronger model.
- Add speech-to-text summaries when transcription is enabled.
- Add GPS/date metadata extraction when available.
- Add object/action classification.
- Add landmark recognition.

### Better Story Planning

- Give DeepSeek a smaller, cleaner summary instead of raw analysis blobs.
- Add a second "critic" pass that checks story plan quality.
- Score each voiceover segment for audience appeal.
- Let the user choose TikTok, family archive, cinematic, funny, or documentary style.
- Add hard duration targets like 15s, 30s, 60s.

### Better Rendering

- Add true xfade transitions.
- Burn captions into video when `burn_captions=true`.
- Add subtitle style presets.
- Add music bed selection.
- Beat-sync cuts to music.
- Normalize original clip audio before mixing narration.
- Support per-segment speed changes.
- Create mobile-first 9:16 previews by default.

### Better UX

- Add thumbnails to clip cards.
- Let user reorder clips with drag/drop.
- Let user edit each voiceover segment.
- Let user regenerate only one segment.
- Show why a clip was selected.
- Show whether Gemini vision, heuristic analysis, or fallback was used.
- Add "new project" and "delete project" confirmations.

### Better Production Architecture

- Move background jobs to Celery, RQ, Dramatiq, or a hosted queue.
- Store sessions/projects in Postgres.
- Store media in object storage.
- Add real user accounts.
- Add per-user project ownership.
- Add structured logs.
- Add retry state and job cancellation.
- Add deployment health checks.

## Debugging Guide

If the Plan screen shows `FALLBACK`:

- Check `TRIPSTORY_LLM_PROVIDER`.
- Check `DEEPSEEK_API_KEY`.
- Check `TRIPSTORY_DEEPSEEK_MODEL`.
- Restart the backend after changing `.env`.
- Look at backend logs for HTTP errors.

If voiceover is generic:

- Check whether clip analysis has `semantic_source=gemini_vision`.
- If it says `heuristic`, Gemini was not used.
- Check `GEMINI_API_KEY`.
- Check `TRIPSTORY_ENABLE_VISION_ANALYSIS=1`.
- Check upload happened after the env was configured, or regenerate the plan to refresh missing semantics.

If video renders but has no narration:

- Check `TRIPSTORY_TTS_PROVIDER=openai`.
- Check `OPENAI_API_KEY`.
- Check backend logs for TTS 429 or auth errors.
- Rendering still succeeds without narration.

If the web page is blank:

- Run `cd mobile && npm run typecheck`.
- Check browser console.
- Check API URL in the top bar.
- Restart Expo with `npm run web -- --clear --port 8081`.

If backend tests call real APIs:

- Tests should clear provider env after importing `api_server.py`.
- Keep `.env` ignored.
- Do not hard-code keys in tests.

## Code Change Checklist

Before pushing:

```bash
git status --short
.conda/trendsync-py312/bin/python -m unittest discover -s tests
cd mobile && npm run typecheck
```

Check that these are not staged:

- `.env`
- `.conda/`
- `trip_sessions/`
- `trip_sessions.sqlite3`
- `trip_sessions_sessions.json`
- `mobile/node_modules/`

Add new backend behavior tests in `tests/test_tripstory_api.py`.

Add new frontend shapes in `mobile/src/types.ts` before using them in `mobile/App.tsx`.

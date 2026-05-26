# TripStory AI: Multilingual Holiday Recap Studio

TripStory AI turns a pile of holiday clips into a polished travel recap plan and stitched video.

The new product flow is:

1. Upload clips and videos from a trip.
2. Answer context questions:
   - Where did you go?
   - How long was the trip?
   - Which places did you visit?
   - Who was there?
   - What moments mattered most?
   - What language and tone should the voiceover use?
3. Generate a multilingual narrative arc, edit notes, and voiceover script.
4. Render a simple final recap video from the uploaded clips.

The LLM layer is vendor-neutral. By default the app works with a deterministic fallback, but you can connect any OpenAI-compatible chat completions endpoint.

---

## Architecture

```
Mobile App ──► FastAPI Session API ──► Vendor-Neutral LLM Brain
    │                 │                         │
    │                 ├── media upload          ├── OpenAI-compatible endpoint
    │                 ├── trip context          └── local fallback
    │                 ├── story plan
    │                 └── video render
    │
    └── Upload -> Context -> Story -> Video
```

## Key Files

| File | Purpose |
|------|---------|
| `api_server.py` | FastAPI app for trip sessions, media upload, story generation, and rendering |
| `llm_provider.py` | Vendor-neutral OpenAI-compatible chat client |
| `trip_story.py` | Multilingual narrative and voiceover generation |
| `trip_renderer.py` | Lightweight video assembly from uploaded clips |
| `mobile/App.tsx` | Expo mobile UI for the TripStory workflow |
| `mobile/src/api.ts` | Mobile API client |
| `mobile/src/types.ts` | Trip session, context, media, and story types |

Legacy trend-analysis modules are still present in the repository for reference, but the active mobile/API product is now TripStory.

## Environment Setup

Recommended Miniconda setup from the repository root:

```bash
conda env create -p "$PWD/.conda/trendsync-py312" -f environment.yml
conda activate "$PWD/.conda/trendsync-py312"
python -m pip install -r requirements.txt
```

The Conda environment provides Python 3.12, `ffmpeg`, Node.js, and npm. Python package dependencies are installed with pip from `requirements.txt`.

If your shell has user-site Python packages visible, keep the Conda environment isolated while installing or running:

```bash
export PYTHONNOUSERSITE=1
```

## Run The API

```bash
python -m uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Optional LLM configuration:

```bash
export TRIPSTORY_LLM_URL="http://localhost:8000/v1"
export TRIPSTORY_LLM_MODEL="your-model-name"
export TRIPSTORY_LLM_API_KEY="optional-key"
```

If `TRIPSTORY_LLM_URL` is not set, TripStory uses a local fallback that still returns a usable narrative plan.

## Run The Mobile App

```bash
cd mobile
npm ci
npm run web -- --clear --port 8081
```

Default API URL:

- iOS/Web: `http://localhost:8010`
- Android emulator: `http://10.0.2.2:8010`

## Current Output

TripStory renders a simple stitched recap video and saves the generated story plan beside it as JSON. The voiceover script is ready for narration or a future TTS provider. The LLM and future TTS layer are intentionally vendor-neutral.

## Implemented Now

- FastAPI session API with health check, session creation, context save, media upload, story generation, and render endpoints.
- Expo mobile app for connecting to the API, uploading video files, entering trip context, choosing voiceover language, generating a story plan, and previewing the rendered output.
- Vendor-neutral OpenAI-compatible LLM client with a deterministic local fallback when no LLM endpoint is configured.
- Multilingual story-plan generation contract with title, language, tone, narrative arc, voiceover script, edit notes, and clip plan.
- Basic video rendering that concatenates uploaded video clips with `ffmpeg` when available and writes the story plan as JSON beside the final video.
- File-backed session persistence so API restarts can recover existing MVP projects.
- Backend smoke test covering session creation, context save, upload, story generation, render, and persistence reload.

## Not Implemented Yet

- Real text-to-speech narration and audio mixing. The app generates a voiceover script, but it does not synthesize speech or attach narration to the rendered video.
- Clip intelligence. Uploaded videos are not yet analyzed for scenes, faces, landmarks, quality, speech, audio levels, or best moments.
- Story-aware editing. The current renderer stitches clips in upload order; it does not trim to beats, match clips to the generated clip plan, add transitions, captions, subtitles, maps, dates, or music.
- Database-backed multi-user project storage. MVP sessions persist to JSON, but there is no production database, account isolation, or project permissions yet.
- User accounts, project library, sharing, permissions, and authentication.
- Production hardening for large uploads, background job queues, retries, progress percentages, cleanup policies, and observability.
- Mobile polish such as project history, drag-and-drop clip ordering, favorite clip markers, timeline editing, export controls, and native share/download flows.
- The older TrendFlow TikTok analysis modules are not integrated into the new TripStory mobile/API flow.

## Development Roadmap

1. Stabilize the TripStory MVP: keep the backend smoke flow and mobile typecheck passing, and add a small manual QA checklist for real device uploads.
2. Add production persistence and project management: move session metadata from JSON to SQLite or Postgres, keep durable project metadata, support project reopen, and add cleanup for old media.
3. Improve rendering: use the generated clip plan to order and trim clips, normalize audio, add basic transitions, burn captions/subtitles, and export consistent portrait/landscape formats.
4. Add narration: integrate a vendor-neutral TTS interface, generate voiceover audio, mix narration under original ambience/music, and store the final audio assets.
5. Add media understanding: extract thumbnails, durations, scene boundaries, blur/quality signals, speech transcripts, GPS/date metadata when available, and suggested highlights.
6. Build editing controls in mobile: reorder clips, mark favorites, edit the script, choose tone/language, select output aspect ratio, and preview timeline changes before render.
7. Prepare for production: move long-running work to a queue, add upload limits and resumable uploads, add auth, add deployment docs, and add monitoring/logging.

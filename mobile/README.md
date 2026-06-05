# TripStory Mobile

Expo client for creating narrated holiday recap videos from uploaded trip clips.

## Run

Start from the repository root with the Conda environment active:

```bash
conda activate "$PWD/.conda/trendsync-py312"
export PYTHONNOUSERSITE=1
```

Start the Python API:

```bash
python -m uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Then install the locked mobile dependencies and run the mobile app:

```bash
cd mobile
npm ci
npm run web -- --clear --port 8081
```

Android emulator default API URL:

```text
http://10.0.2.2:8010
```

Physical Android device:

```text
http://<your-computer-lan-ip>:8010
```

## Flow

The app follows the server session phase:

```text
collecting_context -> uploading -> ready_to_plan -> planning
-> ready_to_render -> rendering -> complete
```

Users upload trip clips, answer travel-context questions, generate a multilingual voiceover plan, and render a simple recap video.

## AI Providers

The story form has provider cards for:

- Local fallback: no backend key.
- OpenAI: uses `OPENAI_API_KEY` from the API server environment.
- Gemini: uses `GEMINI_API_KEY` from the API server environment.
- DeepSeek: uses `DEEPSEEK_API_KEY` from the API server environment.

Provider keys are configured in the backend `.env` file. The frontend does not expose or submit API keys.

Recommended backend split: set `TRIPSTORY_LLM_PROVIDER=deepseek` with `DEEPSEEK_API_KEY` for story generation, and set `TRIPSTORY_VISION_PROVIDER=gemini` with `GEMINI_API_KEY` for sampled video-frame analysis.

## Current Scope

Implemented:

- API connection and session creation.
- Video file upload through Expo DocumentPicker.
- Trip context form with destination, dates, companions, highlights, tone, audience, language, notes, AI provider, and model override.
- Clip intelligence display with quality, scene, audio, best-moment, scenic candidate, and optional speech-transcript signals.
- Clip intelligence display with optional backend visual summaries, visible subjects, scenes, and smart moment descriptions.
- Narrative plan display with voiceover, narrative arc, edit notes, LLM smart edit decisions, and the voiceover line assigned to each timeline segment.
- Render request and video preview through Expo Video, with generated narration mixed in when backend TTS is configured.
- Project library, reopen flow, favorite clip markers, timeline up/down ordering, export aspect-ratio controls, subtitle generation toggle, share action, and render progress display.

Not implemented yet:

- Full login, teams, billing, roles, and native account management.
- Native camera capture inside the TripStory flow.
- Drag-and-drop gestures, full timeline trimming, native share/download sheets, and offline/resumable uploads.
- TTS voice selection, generated narration playback controls, music selection, and dedicated landmark classification.

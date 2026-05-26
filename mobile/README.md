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

## Current Scope

Implemented:

- API connection and session creation.
- Video file upload through Expo DocumentPicker.
- Trip context form with destination, dates, companions, highlights, tone, audience, language, notes, and model override.
- Narrative plan display with voiceover, narrative arc, and edit notes.
- Render request and video preview through Expo Video.

Not implemented yet:

- Login, project history, or persistent mobile project library.
- Native camera capture inside the TripStory flow.
- Clip reordering, favorite markers, trimming, timeline editing, or aspect-ratio/export controls.
- TTS voice selection, generated narration playback, subtitles, music, or share/download actions.
- Offline mode, resumable uploads, and detailed render-progress percentages.

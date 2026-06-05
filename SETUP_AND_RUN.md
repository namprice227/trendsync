# TripStory MVP Setup And Run

TripStory is the active MVP in this repository. It provides a FastAPI backend and an Expo mobile/web client for turning uploaded trip clips into a narrated holiday recap plan and a simple stitched video.

The older TrendFlow TikTok analysis and AMD/vLLM modules are still in the repository for reference, but they are not part of the current TripStory mobile/API MVP.

## 1. Miniconda Environment

Use the repo-local Conda environment from the repository root:

```bash
conda env create -p "$PWD/.conda/trendsync-py312" -f environment.yml
conda activate "$PWD/.conda/trendsync-py312"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

This installs Python 3.12, `ffmpeg`, Node.js, and npm through Conda. The Python application dependencies are installed from `requirements.txt` with pip.

If Conda or pip sees user-site packages from outside the environment, isolate the shell before installing or running commands:

```bash
export PYTHONNOUSERSITE=1
```

If Conda tries to write cache files outside the repository in a restricted shell, redirect its caches into `.conda/`:

```bash
XDG_CACHE_HOME="$PWD/.conda/cache" \
CONDA_PKGS_DIRS="$PWD/.conda/pkgs" \
CONDA_ENVS_PATH="$PWD/.conda/envs" \
conda env create -p "$PWD/.conda/trendsync-py312" -f environment.yml
```

### venv Alternative

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Optional LLM Providers

TripStory works without an LLM server by using a deterministic local fallback.

Use a local `.env` file from the repository root:

```bash
cp .env.example .env
```

Edit `.env`, set `TRIPSTORY_LLM_PROVIDER=deepseek`, fill in `DEEPSEEK_API_KEY`, and fill in `GEMINI_API_KEY` for video-frame understanding. The API loads `.env` on startup. The frontend only selects the provider/model; it does not receive or submit provider API keys.

When story generation succeeds with the configured backend provider, the Plan screen shows `Story brain` as the provider name. If it shows `FALLBACK`, check the warning text on that screen and your `.env` key/provider settings.

LLM calls are serialized server-side to reduce `429 Too Many Requests` errors. You can slow them down further:

```bash
TRIPSTORY_LLM_MIN_INTERVAL_SECONDS=5
TRIPSTORY_LLM_MAX_RETRIES=3
TRIPSTORY_LLM_TIMEOUT=120
TRIPSTORY_STORY_MAX_TOKENS=4096
```

If DeepSeek is configured but the Plan screen says the provider returned an empty response, increase `TRIPSTORY_STORY_MAX_TOKENS`. Reasoning models can spend part of the output budget before producing the final JSON. If the warning is a read timeout, increase `TRIPSTORY_LLM_TIMEOUT` and retry.

Logging is enabled in the API and worker terminals by default:

```bash
TRIPSTORY_LOG_LEVEL=INFO
TRIPSTORY_LOG_HTTP_REQUESTS=1
TRIPSTORY_LOG_FILE=
TRIPSTORY_LOG_API_PAYLOADS=0
```

Set `TRIPSTORY_LOG_FILE=/tmp/tripstory.log` to also write logs to a file, then watch it with:

```bash
tail -f /tmp/tripstory.log
```

During a generation or render, watch the API and worker terminals for `http_request_complete`, `job_progress`, `llm_request_attempt`, `tts_request_attempt`, and render events such as `render_segment_created`. Session polling logs include `session_phase`, `session_progress_percent`, `active_job_state`, and `active_job_step`, which are the fastest way to distinguish a queued job from a blocked worker. To confirm only one LLM or TTS call is active at a time, verify each `llm_request_attempt` or `tts_request_attempt` is followed by a completion/retry line before the next attempt starts. Logs include provider/model/status/elapsed metadata, not API keys, full prompts, full scripts, or uploaded file contents.

Local SQLite and ffmpeg safeguards:

```bash
TRIPSTORY_SESSION_DB=trip_sessions.sqlite3
TRIPSTORY_SQLITE_TIMEOUT_SECONDS=20
TRIPSTORY_FFMPEG_PROBE_TIMEOUT=30
TRIPSTORY_FFMPEG_AUDIO_TIMEOUT=45
TRIPSTORY_FFMPEG_RENDER_TIMEOUT=300
TRIPSTORY_FFMPEG_AUDIO_MIX_TIMEOUT=300
TRIPSTORY_FFMPEG_BIN=
TRIPSTORY_FFPROBE_BIN=
```

The API and RQ worker both read and write SQLite. Connections enable WAL mode and a busy timeout so the local database can handle concurrent API polling and worker progress updates. ffmpeg probes are also bounded by timeouts; media commands resolve `ffmpeg` and `ffprobe` from `PATH`, then from the active Python environment's `bin` directory. Audio-level probing runs with `-nostdin`, `stdin=DEVNULL`, and audio-only mapping so a bad video stream or terminal job-control issue cannot occupy the worker indefinitely after restart.

Default provider models:

- OpenAI: `gpt-4o-mini`
- Gemini: `gemini-2.0-flash`
- DeepSeek: `deepseek-v4-pro`

You can also configure keys through exported environment variables:

```bash
export TRIPSTORY_LLM_PROVIDER="deepseek"   # openai, gemini, deepseek, local, or custom
export DEEPSEEK_API_KEY="your-deepseek-key"
export TRIPSTORY_DEEPSEEK_MODEL="deepseek-v4-pro"
export TRIPSTORY_DEEPSEEK_THINKING="enabled"
export TRIPSTORY_DEEPSEEK_REASONING_EFFORT="high"
export GEMINI_API_KEY="your-gemini-key"
export TRIPSTORY_VISION_PROVIDER="gemini"
export TRIPSTORY_ENABLE_VISION_ANALYSIS=1
```

Use `GEMINI_API_KEY` for Gemini and `DEEPSEEK_API_KEY` for DeepSeek. Optional model overrides are `TRIPSTORY_OPENAI_MODEL`, `TRIPSTORY_GEMINI_MODEL`, and `TRIPSTORY_DEEPSEEK_MODEL`.

Frame analysis uses Gemini by default when `GEMINI_API_KEY` is present:

```bash
TRIPSTORY_VISION_PROVIDER=gemini
TRIPSTORY_VISION_MODEL=gemini-2.0-flash
TRIPSTORY_VISION_MAX_FRAMES=3
TRIPSTORY_VISION_MIN_INTERVAL_SECONDS=5
```

Narration uses server-side TTS when configured. Recommended Gemini TTS setup:

```bash
TRIPSTORY_TTS_PROVIDER=gemini
TRIPSTORY_TTS_MODEL=gemini-3.1-flash-tts-preview
TRIPSTORY_TTS_VOICE=Kore
```

Gemini TTS uses `GEMINI_API_KEY` and outputs `voiceover.wav`. OpenAI TTS remains available with `TRIPSTORY_TTS_PROVIDER=openai`, `OPENAI_API_KEY`, `gpt-4o-mini-tts`, and a voice such as `coral`.

Clip speech transcription is optional and off by default because it sends extracted audio to OpenAI:

```bash
TRIPSTORY_ENABLE_TRANSCRIPTION=1
```

To use any other OpenAI-compatible chat completions endpoint:

```bash
export TRIPSTORY_LLM_PROVIDER="custom"
export TRIPSTORY_LLM_URL="http://localhost:8000/v1"
export TRIPSTORY_LLM_MODEL="your-model-name"
export TRIPSTORY_LLM_API_KEY="optional-key"
```

The client automatically appends `/chat/completions` when the base URL does not include it.

## 3. Storage

By default, uploaded media is stored in:

```text
trip_sessions/
```

Session metadata is stored outside the public static media directory:

```text
trip_sessions_sessions.json
```

Override these paths when needed:

```bash
export TRIPSTORY_MEDIA_DIR="/path/to/media"
export TRIPSTORY_SESSION_STORE="/path/to/sessions.json"
```

## 4. Run Redis, Worker, And API

Story generation and rendering are queued through RQ. Start Redis first:

```bash
redis-server
```

The Conda environment installs Redis from `environment.yml`. If you use the venv path instead, install Redis through your OS package manager or Docker.

In a second terminal, start the TripStory worker:

```bash
python worker.py
```

Keep this worker running in the foreground or under a process supervisor. If the terminal suspends the worker or one of its children, the queue can stop moving even though the API still responds. In `ps`, `STAT T` or `Tl` on `python worker.py` or `ffmpeg` means the process is stopped, not doing slow work.

In a third terminal, start the API:

```bash
python -m uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Health check:

```bash
curl http://127.0.0.1:8010/health
```

Expected response:

```json
{"status":"ok","product":"TripStory"}
```

## 5. Run The Mobile/Web App

```bash
cd mobile
npm ci
npm run web -- --clear --port 8081
```

Default API URLs:

- Web/iOS simulator: `http://localhost:8010`
- Android emulator: `http://10.0.2.2:8010`
- Physical device: `http://<your-computer-lan-ip>:8010`

## 6. Verify The MVP

Run the backend smoke test from the repository root:

```bash
python -m unittest discover -s tests
```

Run the mobile typecheck:

```bash
cd mobile
npm run typecheck
```

## 7. MVP Flow

1. Start Redis.
2. Start the TripStory worker.
3. Start the API.
4. Start the mobile/web app.
5. Upload at least one video clip.
6. Save trip context.
7. Generate a narrative plan with smart edit decisions.
8. Choose timeline favorites/order and export ratio.
9. Render the holiday recap video.
10. Preview the video. If TTS is configured, generated narration is mixed into the render.

## 8. Known MVP Limits

- Auth is token/header based for local MVP use, not a full identity provider.
- Clip intelligence is local and heuristic. It names likely landmarks from trip context and scenic frames, but it does not yet run a true landmark-recognition model.
- Sessions persist to SQLite with JSON backup compatibility, but there is no full account system or production role model.
- Long-running generation/rendering uses RQ + Redis with a lightweight SQLite jobs table, not a fully distributed production workflow system.

## 9. Quick Troubleshooting

If rendering is stuck on the frontend:

```bash
sqlite3 trip_sessions.sqlite3 "select id, session_id, type, state, progress_percent, current_step, error, rq_job_id, attempts, datetime(updated_at, 'unixepoch', 'localtime') from jobs order by updated_at desc limit 10;"
ps -ef
```

Look for one active `story_generation` or `render` job ahead of the job you care about. With one worker, that job blocks every queued job behind it.

If ffmpeg looks stuck, test the media file directly:

```bash
timeout 20 .conda/trendsync-py312/bin/ffmpeg -nostdin -hide_banner -i trip_sessions/<session_id>/media/<file>.mp4 -vn -af volumedetect -f null -
```

If the direct command finishes quickly but the worker remains stuck, restart the worker so it loads current code and clears the stopped child process.

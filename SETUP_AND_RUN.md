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
```

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

Narration uses server-side OpenAI TTS when `OPENAI_API_KEY` is configured:

```bash
TRIPSTORY_TTS_PROVIDER=openai
TRIPSTORY_TTS_MODEL=gpt-4o-mini-tts
TRIPSTORY_TTS_VOICE=coral
```

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

## 4. Run The API

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

1. Start the API.
2. Start the mobile/web app.
3. Upload at least one video clip.
4. Save trip context.
5. Generate a narrative plan with smart edit decisions.
6. Choose timeline favorites/order and export ratio.
7. Render the holiday recap video.
8. Preview the video. If TTS is configured, generated narration is mixed into the render.

## 8. Known MVP Limits

- Auth is token/header based for local MVP use, not a full identity provider.
- Background work still uses FastAPI background tasks, not a durable distributed queue.
- Clip intelligence is local and heuristic. It names likely landmarks from trip context and scenic frames, but it does not yet run a true landmark-recognition model.
- Sessions persist to SQLite with JSON backup compatibility, but there is no full account system or production role model.
- Long-running generation/rendering uses FastAPI background tasks, not a production queue.

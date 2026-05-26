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

Edit `.env`, set `TRIPSTORY_LLM_PROVIDER` to `openai`, `gemini`, or `deepseek`, and fill in the matching key. The API loads `.env` on startup. The frontend only selects the provider/model; it does not receive or submit provider API keys.

Default provider models:

- OpenAI: `gpt-4o-mini`
- Gemini: `gemini-2.0-flash`
- DeepSeek: `deepseek-chat`

You can also configure keys through exported environment variables:

```bash
export TRIPSTORY_LLM_PROVIDER="openai"   # openai, gemini, deepseek, local, or custom
export OPENAI_API_KEY="your-openai-key"
```

Use `GEMINI_API_KEY` for Gemini and `DEEPSEEK_API_KEY` for DeepSeek. Optional model overrides are `TRIPSTORY_OPENAI_MODEL`, `TRIPSTORY_GEMINI_MODEL`, and `TRIPSTORY_DEEPSEEK_MODEL`.

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
5. Generate a narrative plan.
6. Render the holiday recap video.
7. Preview the video and use the generated voiceover script for manual narration or a future TTS step.

## 8. Known MVP Limits

- The generated voiceover is text only; speech synthesis and audio mixing are not implemented yet.
- The renderer stitches clips in upload order; it does not yet trim clips to the generated story plan.
- Sessions persist to JSON, but there is no user account system or multi-user permission model.
- Long-running generation/rendering uses FastAPI background tasks, not a production queue.

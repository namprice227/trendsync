# TrendFlow Setup And Run Guide

This is the single setup/run file for the whole repo: Python backend, Gradio web UI, Expo mobile app, dummy/offline mode, and AMD GPU server mode.

## 0. What Runs Where

TrendFlow has three runnable surfaces:

| Surface | File / folder | Default port | Purpose |
|---|---:|---:|---|
| Gradio web app | `app.py` | `7860` | Full desktop/web workflow |
| Mobile API server | `api_server.py` | `8010` | Backend for the Expo mobile app |
| Expo mobile app | `mobile/` | Expo dev server | Android camera-first guided UI |

Optional model servers:

| Service | Default port | Used for |
|---|---:|---|
| Main vLLM server | `8000` | trend analysis, script, evaluation |
| Director vLLM server | `8001` | faster real-time/director feedback |

The app can run without real vLLM by using the dummy VLM server. CPU features such as download, beat/cut analysis, MediaPipe pose extraction, optical flow, and rendering still work locally.

## 1. Prerequisites

Required:

- Linux/macOS/WSL2 shell for Python backend.
- Python 3.12. Do not use Python 3.13 for the main app because `mediapipe==0.10.14` needs the legacy `mp.solutions.pose` API.
- Conda or Miniconda.
- `ffmpeg`.

Mobile:

- Node.js 20.19.x or newer compatible with Expo SDK 55.
- npm.
- Android Studio/emulator or a physical Android device with Expo/dev build.

AMD GPU server:

- Linux server with ROCm-compatible AMD GPU, such as MI300X.
- ROCm installed and visible through `rocm-smi`.
- Docker with access to `/dev/kfd` and `/dev/dri`, or a working ROCm Python environment.
- Hugging Face access/token if the selected model requires it.

## 2. Clone

```bash
git clone https://github.com/namprice227/trendsync
cd trendsync
```

## 3. Python Backend Setup

Preferred one-command setup:

```bash
./setup.sh
```

That script creates `.conda/trendsync-py312`, installs `ffmpeg`, installs `requirements.txt`, runs `pip check`, and verifies MediaPipe pose.

Manual setup:

```bash
conda create -y -p "$PWD/.conda/trendsync-py312" python=3.12 pip
conda activate "$PWD/.conda/trendsync-py312"
conda install -y -c conda-forge ffmpeg
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

Verify MediaPipe:

```bash
MPLCONFIGDIR=/tmp/mpl python - <<'PY'
import mediapipe as mp
print("mediapipe", mp.__version__)
print("has solutions:", hasattr(mp, "solutions"))
print("has pose:", hasattr(mp.solutions, "pose"))
pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1)
pose.close()
print("pose constructor ok")
PY
```

Expected:

```text
mediapipe 0.10.14
has solutions: True
has pose: True
pose constructor ok
```

## 4. Run Local Dummy Mode

Use this on a laptop or CPU-only machine when AMD GPU, ROCm, or vLLM is not available.

### 4.1 Dummy Gradio Web UI

```bash
bash run_dummy_ui.sh
```

This starts:

- Dummy analysis endpoint: `http://127.0.0.1:8000/v1/chat/completions`
- Dummy director endpoint: `http://127.0.0.1:8001/v1/chat/completions`
- Gradio UI: `http://127.0.0.1:7860`

### 4.2 Dummy Mobile API

For the Expo app, start the dummy servers and `api_server.py`:

```bash
# Terminal 1
conda activate "$PWD/.conda/trendsync-py312"
python dummy_vllm_server.py --port 8000 --model Qwen/Qwen3.6-35B-A3B

# Terminal 2
conda activate "$PWD/.conda/trendsync-py312"
python dummy_vllm_server.py --port 8001 --model mistralai/Pixtral-12B-2409

# Terminal 3
conda activate "$PWD/.conda/trendsync-py312"
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://127.0.0.1:8001/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
MPLCONFIGDIR=/tmp/mpl uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Then run the Expo app from `mobile/` and point it at `http://10.0.2.2:8010` for Android emulator or `http://<computer-lan-ip>:8010` for a physical device.

## 5. Run The Gradio Web App

Without a real VLM server:

```bash
conda activate "$PWD/.conda/trendsync-py312"
MPLCONFIGDIR=/tmp/mpl python app.py
```

Open:

```text
http://127.0.0.1:7860
```

On a remote VM, open:

```text
http://<VM-IP>:7860
```

If port `7860` is busy:

```bash
MPLCONFIGDIR=/tmp/mpl python -c "import app; app.launch_demo(server_name='0.0.0.0', server_port=7861, share=False)"
```

## 6. Run The Mobile API Server

The Expo app talks to `api_server.py`, not directly to Gradio.

```bash
conda activate "$PWD/.conda/trendsync-py312"
MPLCONFIGDIR=/tmp/mpl uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Health check:

```bash
curl http://127.0.0.1:8010/health
```

Expected:

```json
{"status":"ok"}
```

Create a session:

```bash
curl -X POST http://127.0.0.1:8010/sessions
```

The returned JSON includes `phase` and `screen`. The mobile app follows these automatically:

```text
awaiting_reference -> analyzing -> ready_to_film -> needs_adjustment
-> ready_to_record -> uploading -> rendering -> evaluating -> complete
```

## 7. Run The Expo Mobile App

Install:

```bash
cd mobile
npm install
```

Start Expo:

```bash
npm run start
```

Run on Android:

```bash
npm run android
```

Default API URL inside the app:

| Android target | API URL |
|---|---|
| Android emulator, API on same machine | `http://10.0.2.2:8010` |
| Physical Android device, API on LAN | `http://<your-computer-lan-ip>:8010` |
| API on remote AMD server | `http://<server-ip-or-dns>:8010` |

If using a physical phone, do not use `127.0.0.1` or `localhost`; that points to the phone itself. Start `api_server.py` with `--host 0.0.0.0`, allow port `8010` through the firewall, then enter the machine's LAN/server IP in the app header.

## 8. Run On An AMD GPU Server

Recommended topology:

```text
AMD GPU server:
  - vLLM main model on :8000
  - optional vLLM director model on :8001
  - TrendFlow Python backend / mobile API on :8010

Laptop or phone:
  - Browser opens Gradio :7860, or
  - Expo Android app connects to :8010
```

### 8.1 Verify ROCm

On the AMD server:

```bash
rocm-smi
```

You should see the AMD GPU, VRAM, and current memory usage.

### 8.2 Start vLLM With ROCm Docker

Official vLLM ROCm Docker images use the `vllm/vllm-openai-rocm` repository. The important AMD device flags are `/dev/kfd`, `/dev/dri`, `--group-add=video`, `--ipc=host`, and relaxed seccomp for ROCm profiling/debug access.

Set Hugging Face token if needed:

```bash
export HF_TOKEN="<your-huggingface-token>"
```

Start the main VLM server:

```bash
docker run --rm \
  --group-add=video \
  --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --device /dev/kfd \
  --device /dev/dri \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  --env "HF_TOKEN=$HF_TOKEN" \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai-rocm:latest \
  --model Qwen/Qwen3.6-35B-A3B \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.65 \
  --max-model-len 49152 \
  --generation-config vllm
```

If your model ID differs, keep the served model and the TrendFlow env var in sync.

Test vLLM:

```bash
curl http://127.0.0.1:8000/v1/models
```

Optional second director model:

```bash
docker run --rm \
  --group-add=video \
  --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --device /dev/kfd \
  --device /dev/dri \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  --env "HF_TOKEN=$HF_TOKEN" \
  -p 8001:8000 \
  --ipc=host \
  vllm/vllm-openai-rocm:latest \
  --model mistralai/Pixtral-12B-2409 \
  --gpu-memory-utilization 0.20 \
  --max-model-len 16384 \
  --generation-config vllm
```

If Pixtral needs Mistral loader flags, add these after the image name:

```bash
--tokenizer-mode mistral \
--load-format mistral \
--limit-mm-per-prompt image=4
```

If you see a free-memory error, check `rocm-smi`, stop the first vLLM container, and relaunch it with lower `--gpu-memory-utilization`, for example `0.55`.

### 8.3 Point TrendFlow At vLLM

In the shell where you start `app.py` or `api_server.py`:

```bash
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_EVALUATOR_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_SCRIPT_MODEL="Qwen/Qwen3.6-35B-A3B"

# Use this only if the second director server is running.
export TRENDFLOW_DIRECTOR_VLLM_URL="http://127.0.0.1:8001/v1/chat/completions"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
```

Single-model mode:

```bash
export TRENDFLOW_DIRECTOR_VLLM_URL="$TRENDFLOW_VLLM_URL"
export TRENDFLOW_DIRECTOR_MODEL="$TRENDFLOW_ANALYSIS_MODEL"
```

### 8.4 Start TrendFlow On The AMD Server

Set up Python once:

```bash
./setup.sh
conda activate "$PWD/.conda/trendsync-py312"
```

Run Gradio:

```bash
MPLCONFIGDIR=/tmp/mpl python app.py
```

Run mobile API:

```bash
MPLCONFIGDIR=/tmp/mpl uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Open firewall/security group ports as needed:

| Port | Service |
|---:|---|
| `7860` | Gradio web UI |
| `8010` | mobile API |
| `8000` | main vLLM, usually keep private |
| `8001` | director vLLM, usually keep private |

For security, expose `7860`/`8010` only to your IP or private network. Keep vLLM ports private unless you add auth/network controls.

### 8.5 Run Backend Locally But vLLM Remotely

If vLLM runs on the AMD server but the TrendFlow backend runs on your laptop, use SSH tunnels:

```bash
ssh -L 8000:127.0.0.1:8000 -L 8001:127.0.0.1:8001 user@<amd-server>
```

Then locally:

```bash
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://127.0.0.1:8001/v1/chat/completions"
MPLCONFIGDIR=/tmp/mpl python app.py
```

## 9. Environment Variables

| Variable | Default | Meaning |
|---|---|---|
| `TRENDFLOW_VLLM_URL` | `http://localhost:8000/v1/chat/completions` | Main vLLM endpoint |
| `TRENDFLOW_DIRECTOR_VLLM_URL` | same as main | Optional fast director endpoint |
| `TRENDFLOW_ANALYSIS_MODEL` | `Qwen/Qwen3.6-35B-A3B` | Model for trend analysis |
| `TRENDFLOW_DIRECTOR_MODEL` | `Qwen/Qwen3.6-35B-A3B` | Model for director feedback |
| `TRENDFLOW_EVALUATOR_MODEL` | `Qwen/Qwen3.6-35B-A3B` | Model for judging final video |
| `TRENDFLOW_SCRIPT_MODEL` | `Qwen/Qwen3.6-35B-A3B` | Model for script/caption |
| `TRENDFLOW_DIRECTOR_VLM_INTERVAL` | `3.0` | Seconds between VLM director checks |
| `TRENDFLOW_ANALYSIS_TIMEOUT` | `120` | Analysis VLM timeout |
| `TRENDFLOW_DIRECTOR_TIMEOUT` | `30` | Director VLM timeout |
| `TRENDFLOW_EVALUATOR_TIMEOUT` | `60` | Evaluation VLM timeout |
| `TRENDFLOW_SCRIPT_TIMEOUT` | `60` | Script VLM timeout |
| `TRENDFLOW_MOBILE_DIR` | `mobile_sessions` | API upload/render storage |
| `TRENDFLOW_API_PORT` | `8010` | `api_server.py` default when run directly |

## 10. Ports Cheat Sheet

```text
8000  main vLLM OpenAI-compatible server
8001  optional fast director vLLM server
7860  Gradio web UI
8010  FastAPI mobile API
```

## 11. Troubleshooting

### `mediapipe.solutions.pose` missing

You are probably using Python 3.13 or incompatible MediaPipe wheels. Re-run:

```bash
./setup.sh
conda activate "$PWD/.conda/trendsync-py312"
```

### `ffmpeg` not found or audio extraction fails

```bash
conda activate "$PWD/.conda/trendsync-py312"
conda install -y -c conda-forge ffmpeg
```

### `yt-dlp` cannot download a video

Update only if needed:

```bash
python -m pip install --upgrade yt-dlp
```

Some TikTok/Reel URLs may require cookies or may be blocked by the network.

### vLLM memory error on MI300X

Check usage:

```bash
rocm-smi
```

Lower memory caps:

```bash
--gpu-memory-utilization 0.55
```

For dual-model mode, start the larger model first with a conservative cap, then the smaller director model.

### Mobile app cannot reach API

- Emulator: use `http://10.0.2.2:8010`.
- Physical Android: use `http://<server-lan-ip>:8010`.
- Make sure API uses `--host 0.0.0.0`.
- Make sure firewall/security groups allow `8010`.
- Verify from another machine: `curl http://<server-ip>:8010/health`.

### Expo will not install or start

Use Node 20.19.x or newer compatible with Expo SDK 55:

```bash
node --version
npm --version
```

Then:

```bash
cd mobile
npm install
npm run start
```

### WSL1 and Node/npm problems

Use WSL2, native Windows Node, or another Linux/macOS shell. Expo/React Native tooling is not reliable under WSL1.

## 12. Useful Source Files

| File | Purpose |
|---|---|
| `README.md` | Architecture and product overview |
| `setup.sh` | Reproducible Python 3.12 conda setup |
| `requirements.txt` | Python dependencies |
| `app.py` | Gradio UI |
| `api_server.py` | Mobile API and automatic session state machine |
| `mobile/App.tsx` | Expo Android UI |
| `mobile/package.json` | Expo/React Native dependencies |
| `dummy_vllm_server.py` | OpenAI-compatible dummy VLM |
| `run_dummy_ui.sh` | One-command dummy VLM + Gradio run |

## 13. References Used For AMD/vLLM Details

- vLLM OpenAI-compatible server docs: `https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html`
- vLLM ROCm Docker install docs: `https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html?device=rocm`
- AMD ROCm vLLM docs: `https://rocm.docs.amd.com/en/7.12.0-preview/rocm-for-ai/vllm.html`

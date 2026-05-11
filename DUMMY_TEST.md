# TrendFlow Dummy Test Guide

This file is for local or CPU-only testing when the AMD GPU server path is not available.

For the AMD server path, use [SETUP_AND_RUN.md](/home/nam/trendsync/SETUP_AND_RUN.md).

## 1. Set Up Python

```bash
./setup.sh
conda activate "$PWD/.conda/trendsync-py312"
```

## 2. One-Command Dummy Gradio Test

```bash
bash run_dummy_ui.sh
```

This starts:

- Dummy analysis endpoint on `http://127.0.0.1:8000/v1/chat/completions`
- Dummy director endpoint on `http://127.0.0.1:8001/v1/chat/completions`
- Gradio UI on `http://127.0.0.1:7860`

## 3. Manual Dummy Gradio Test

Terminal 1:

```bash
conda activate "$PWD/.conda/trendsync-py312"
python dummy_vllm_server.py --port 8000 --model Qwen/Qwen3.6-35B-A3B
```

Terminal 2:

```bash
conda activate "$PWD/.conda/trendsync-py312"
python dummy_vllm_server.py --port 8001 --model mistralai/Pixtral-12B-2409
```

Terminal 3:

```bash
conda activate "$PWD/.conda/trendsync-py312"
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://127.0.0.1:8001/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
MPLCONFIGDIR=/tmp/mpl python app.py
```

## 4. Manual Dummy Mobile API Test

Terminal 1:

```bash
conda activate "$PWD/.conda/trendsync-py312"
python dummy_vllm_server.py --port 8000 --model Qwen/Qwen3.6-35B-A3B
```

Terminal 2:

```bash
conda activate "$PWD/.conda/trendsync-py312"
python dummy_vllm_server.py --port 8001 --model mistralai/Pixtral-12B-2409
```

Terminal 3:

```bash
conda activate "$PWD/.conda/trendsync-py312"
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://127.0.0.1:8001/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
MPLCONFIGDIR=/tmp/mpl uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Health check:

```bash
curl http://127.0.0.1:8010/health
```

## 5. Expo Mobile Test

From `mobile/`:

Do not run Expo as `root`. React Native DevTools can fail under Electron with Chrome's sandbox restriction when Expo is started as `root`.

```bash
npm install
npx expo-doctor
npx expo install --fix
npx expo start --clear
```

Use:

- `http://10.0.2.2:8010` for Android emulator
- `http://<your-computer-lan-ip>:8010` for a physical Android device

If Expo Go on the phone shows an SDK mismatch, update Expo Go first, then restart the bundler with `npx expo start --clear`. Expo's official SDK docs currently list SDK 55 as the latest stable SDK, and Expo recommends aligning dependencies with `npx expo install --fix`.

## 6. Notes

The dummy server returns deterministic fake responses for style analysis, directing, script, and judging. It is useful for UI and wiring tests, not for real visual analysis.

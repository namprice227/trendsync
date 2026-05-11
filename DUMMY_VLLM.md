# Dummy VLM Server For UI Testing

Use this mode on a laptop or CPU-only machine when AMD GPU, ROCm, or vLLM is not available.

## One-Command UI Test

```bash
bash run_dummy_ui.sh
```

This starts:

- Dummy analysis endpoint: `http://127.0.0.1:8000/v1/chat/completions`
- Dummy director endpoint: `http://127.0.0.1:8001/v1/chat/completions`
- Gradio UI: `http://127.0.0.1:7860`

## Manual Mode

Terminal 1:

```bash
python dummy_vllm_server.py --port 8000 --model Qwen/Qwen3.6-35B-A3B
```

Terminal 2:

```bash
python dummy_vllm_server.py --port 8001 --model mistralai/Pixtral-12B-2409
```

Terminal 3:

```bash
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://127.0.0.1:8001/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
MPLCONFIGDIR=/tmp/mpl python app.py
```

The dummy server returns deterministic style, director, script, and judge responses. It is only for local UI/backend testing, not real visual analysis.

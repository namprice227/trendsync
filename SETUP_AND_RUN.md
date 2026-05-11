# TrendFlow AMD Server Setup And Run

This file is only for the AMD GPU server path.

For dummy/local testing, use [DUMMY_TEST.md](/home/nam/trendsync/DUMMY_TEST.md).

## 1. Clone The Repo

```bash
git clone https://github.com/namprice227/trendsync
cd trendsync
```

## 2. Set Up Python On The AMD Server

Use the repo setup script:

```bash
./setup.sh
```

That creates the Python 3.12 environment at `.conda/trendsync-py312`, installs `ffmpeg`, installs `requirements.txt`, and verifies MediaPipe pose.

Activate the environment:

```bash
conda activate "$PWD/.conda/trendsync-py312"
```

If `conda activate` is not initialized in the shell:

```bash
source /home/nam/miniconda3/bin/activate "$PWD/.conda/trendsync-py312"
```

## 3. Check ROCm

```bash
rocm-smi
```

You should see the AMD GPU and VRAM usage before starting vLLM.

## 4. Enter The ROCm Container

This guide assumes your running container is named `rocm`:

```bash
docker exec -it rocm bash
```

## 5. Download The Qwen Model In The Container

```bash
huggingface-cli download Qwen/Qwen3.6-35B-A3B
```

## 6. Start vLLM In The Container

Run this inside the `rocm` container:

```bash
vllm serve Qwen/Qwen3.6-35B-A3B \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.60 \
  --max-model-len 80072 \
  --served-model-name trend_model
```

The `\` must be the last character on each continued line. Do not leave trailing spaces after it.

## 7. Verify vLLM From The Host

Open another shell on the AMD server host:

```bash
curl http://127.0.0.1:8000/v1/models
```

## 8. Point TrendFlow At vLLM

In the shell where you run TrendFlow:

```bash
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="trend_model"
export TRENDFLOW_EVALUATOR_MODEL="trend_model"
export TRENDFLOW_SCRIPT_MODEL="trend_model"
export TRENDFLOW_DIRECTOR_VLLM_URL="$TRENDFLOW_VLLM_URL"
export TRENDFLOW_DIRECTOR_MODEL="$TRENDFLOW_ANALYSIS_MODEL"
```

## 9. Run The Gradio Web App On The AMD Server

```bash
conda activate "$PWD/.conda/trendsync-py312"
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="trend_model"
export TRENDFLOW_EVALUATOR_MODEL="trend_model"
export TRENDFLOW_SCRIPT_MODEL="trend_model"
export TRENDFLOW_DIRECTOR_VLLM_URL="$TRENDFLOW_VLLM_URL"
export TRENDFLOW_DIRECTOR_MODEL="$TRENDFLOW_ANALYSIS_MODEL"
MPLCONFIGDIR=/tmp/mpl python app.py
```

Default web UI:

```text
http://<amd-server-ip>:7860
```

## 10. Run The Mobile API On The AMD Server

```bash
conda activate "$PWD/.conda/trendsync-py312"
export TRENDFLOW_VLLM_URL="http://127.0.0.1:8000/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="trend_model"
export TRENDFLOW_EVALUATOR_MODEL="trend_model"
export TRENDFLOW_SCRIPT_MODEL="trend_model"
export TRENDFLOW_DIRECTOR_VLLM_URL="$TRENDFLOW_VLLM_URL"
export TRENDFLOW_DIRECTOR_MODEL="$TRENDFLOW_ANALYSIS_MODEL"
MPLCONFIGDIR=/tmp/mpl uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Health check:

```bash
curl http://127.0.0.1:8010/health
```

Default API:

```text
http://<amd-server-ip>:8010
```

## 11. Ports To Open

```text
7860  Gradio web UI
8010  FastAPI mobile API
8000  vLLM server, usually keep private
```

If possible, expose `7860` and `8010` only to your own IP or private network. Keep `8000` private.

## 12. If vLLM Fails On Memory

Check usage:

```bash
rocm-smi
```

Then lower:

```bash
--gpu-memory-utilization 0.55
```

## 13. Useful Endpoints

```text
http://127.0.0.1:8000/v1/models
http://127.0.0.1:8010/health
http://<amd-server-ip>:7860
http://<amd-server-ip>:8010
```

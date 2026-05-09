"""
TrendFlow AI — Centralized Configuration

All model names and API URLs are configurable via environment variables.
This allows switching between models (e.g., Qwen3.6-35B → Qwen2-VL-72B)
without changing any code.

Environment Variables:
  TRENDFLOW_VLLM_URL          - vLLM API endpoint (default: http://localhost:8000/v1/chat/completions)
  TRENDFLOW_ANALYSIS_MODEL    - Model for trend analysis / style extraction (heavy, 72B recommended)
  TRENDFLOW_DIRECTOR_MODEL    - Model for real-time directing feedback (fast, 12B recommended)
  TRENDFLOW_EVALUATOR_MODEL   - Model for final video scoring
  TRENDFLOW_SCRIPT_MODEL      - Model for script/caption generation

Dual-Model Strategy (MI300X 192GB VRAM):
  - Run a 72B model (Qwen2-VL-72B-Instruct) for analysis + evaluation (~144GB)
  - Run a 12B model (Pixtral-12B) on a separate port for fast directing (~24GB)
  - Set TRENDFLOW_DIRECTOR_VLLM_URL to the second port
"""

import os

# --- API Endpoints ---
VLLM_API_URL = os.environ.get(
    "TRENDFLOW_VLLM_URL",
    "http://localhost:8000/v1/chat/completions"
)

# Optional: separate endpoint for the fast director model
DIRECTOR_VLLM_API_URL = os.environ.get(
    "TRENDFLOW_DIRECTOR_VLLM_URL",
    VLLM_API_URL  # defaults to same endpoint
)

# --- Model Names ---
ANALYSIS_MODEL = os.environ.get(
    "TRENDFLOW_ANALYSIS_MODEL",
    "Qwen/Qwen3.6-35B-A3B"
)

DIRECTOR_MODEL = os.environ.get(
    "TRENDFLOW_DIRECTOR_MODEL",
    "Qwen/Qwen3.6-35B-A3B"
)

EVALUATOR_MODEL = os.environ.get(
    "TRENDFLOW_EVALUATOR_MODEL",
    "Qwen/Qwen3.6-35B-A3B"
)

SCRIPT_MODEL = os.environ.get(
    "TRENDFLOW_SCRIPT_MODEL",
    "Qwen/Qwen3.6-35B-A3B"
)

# --- Timeouts (seconds) ---
ANALYSIS_TIMEOUT = int(os.environ.get("TRENDFLOW_ANALYSIS_TIMEOUT", "120"))
DIRECTOR_TIMEOUT = int(os.environ.get("TRENDFLOW_DIRECTOR_TIMEOUT", "30"))
EVALUATOR_TIMEOUT = int(os.environ.get("TRENDFLOW_EVALUATOR_TIMEOUT", "60"))
SCRIPT_TIMEOUT = int(os.environ.get("TRENDFLOW_SCRIPT_TIMEOUT", "60"))

# --- Director Tuning ---
DIRECTOR_VLM_INTERVAL = float(os.environ.get("TRENDFLOW_DIRECTOR_VLM_INTERVAL", "3.0"))

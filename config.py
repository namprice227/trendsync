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

# --- Retry Configuration ---
VLM_MAX_RETRIES = int(os.environ.get("TRENDFLOW_VLM_MAX_RETRIES", "3"))
VLM_RETRY_BACKOFF = float(os.environ.get("TRENDFLOW_VLM_RETRY_BACKOFF", "2.0"))


# ============================================================
# UTILITY: VLM request with exponential backoff (Fix 5)
# ============================================================
import requests
import time as _time

def vlm_request_with_retry(url: str, payload: dict, timeout: int,
                           max_retries: int = None, backoff: float = None):
    """
    Sends a POST request to the VLM endpoint with automatic retry + exponential backoff.
    Returns the response JSON on success, raises on final failure.
    """
    if max_retries is None:
        max_retries = VLM_MAX_RETRIES
    if backoff is None:
        backoff = VLM_RETRY_BACKOFF
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait = backoff ** attempt
                print(f"  VLM request failed (attempt {attempt+1}/{max_retries}), retrying in {wait:.1f}s: {e}")
                _time.sleep(wait)
            else:
                print(f"  VLM request failed after {max_retries} attempts: {e}")
    raise last_error


# ============================================================
# UTILITY: Session cleanup (Fix 3)
# ============================================================
import shutil

def cleanup_session(dirs=None):
    """
    Removes temporary files from previous analysis sessions.
    Called before starting a new trend analysis to prevent storage bloat.
    """
    if dirs is None:
        dirs = ["temp", "recorded_shots"]
    
    for d in dirs:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                os.makedirs(d, exist_ok=True)
                print(f"[Cleanup] Cleared {d}/")
            except Exception as e:
                print(f"[Cleanup] Failed to clear {d}/: {e}")

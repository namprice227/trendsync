#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_PATH="$ROOT_DIR/.conda/trendsync-py312"
ENV_PATH="${TRENDSYNC_CONDA_ENV:-$DEFAULT_ENV_PATH}"
PYTHON_VERSION="${TRENDSYNC_PYTHON_VERSION:-3.12}"
MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"

log() {
  printf '\n[setup] %s\n' "$*"
}

find_conda() {
  if [[ -n "${CONDA_EXE:-}" && -x "${CONDA_EXE}" ]]; then
    printf '%s\n' "$CONDA_EXE"
    return 0
  fi

  if command -v conda >/dev/null 2>&1; then
    command -v conda
    return 0
  fi

  for candidate in \
    "$HOME/miniconda3/bin/conda" \
    "$HOME/anaconda3/bin/conda" \
    "/home/nam/miniconda3/bin/conda" \
    "/opt/conda/bin/conda"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

if ! CONDA_BIN="$(find_conda)"; then
  printf '[setup] ERROR: conda was not found.\n' >&2
  printf '[setup] Install Miniconda/Anaconda or set CONDA_EXE to the conda binary path.\n' >&2
  exit 1
fi

log "Using conda: $CONDA_BIN"
log "Project: $ROOT_DIR"
log "Environment: $ENV_PATH"

mkdir -p "$MPLCONFIGDIR"

if [[ ! -d "$ENV_PATH/conda-meta" ]]; then
  log "Creating Python $PYTHON_VERSION conda environment"
  "$CONDA_BIN" create -y -p "$ENV_PATH" "python=$PYTHON_VERSION" pip
else
  log "Reusing existing conda environment"
fi

log "Installing ffmpeg from conda-forge"
"$CONDA_BIN" install -y -p "$ENV_PATH" -c conda-forge ffmpeg

log "Upgrading pip"
"$CONDA_BIN" run -p "$ENV_PATH" python -m pip install --upgrade pip

log "Installing Python requirements"
"$CONDA_BIN" run -p "$ENV_PATH" python -m pip install -r "$ROOT_DIR/requirements.txt"

log "Checking installed Python packages"
"$CONDA_BIN" run -p "$ENV_PATH" python -m pip check

log "Verifying MediaPipe legacy pose API"
MPLCONFIGDIR="$MPLCONFIGDIR" "$CONDA_BIN" run -p "$ENV_PATH" python - <<'PY'
import mediapipe as mp

print("mediapipe", mp.__version__)
print("has solutions:", hasattr(mp, "solutions"))
print("has pose:", hasattr(mp.solutions, "pose"))

pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1)
pose.close()

print("pose constructor ok")
PY

log "Setup complete"
printf '\nActivate the environment with:\n'
printf '  conda activate "%s"\n' "$ENV_PATH"
printf '\nRun the app with:\n'
printf '  MPLCONFIGDIR=%q python app.py\n' "$MPLCONFIGDIR"

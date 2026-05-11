# 🎬 TrendFlow AI: The Autonomous TikTok Director & Editor

TrendFlow AI is an end-to-end agentic pipeline that watches viral TikTok trends, reverse-engineers their editing math, and acts as a real-time, on-set AI director to help you film and edit your own perfectly synced version.

Built for the [AMD Developer Hackathon](https://lablab.ai/ai-hackathons/amd-developer), optimized for **AMD MI300X** with ROCm.

---

## 📖 How It Works — The Full Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                     TrendFlow AI Pipeline                           │
│                                                                      │
│  TikTok URL ──► ANALYZE ──► FILM ──► RENDER ──► JUDGE               │
│                   │           │         │          │                  │
│                   ▼           ▼         ▼          ▼                  │
│               Style Guide  AI Director  Beat-Synced  Score/10        │
│               + Poses      (Hybrid)    Final Video   + Critique      │
│               + Camera                                               │
│                 Motion                                               │
└──────────────────────────────────────────────────────────────────────┘
```

### Step 1: Trend Analysis (Analyzer)

When you paste a TikTok URL and click **Analyze Trend**, the system runs a multi-stage analysis pipeline:

```
TikTok URL
    │
    ▼
┌─────────────────────────────────────────┐
│ 1. DOWNLOAD VIDEO                       │
│    yt-dlp downloads the full video      │
│    → temp/reference_video.mp4           │
│    (old files are deleted first to      │
│    ensure a fresh download every time)  │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┼───────────┬───────────────────┬───────────────────┐
    ▼            ▼           ▼                   ▼                   ▼
┌────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐
│ AUDIO  │ │ CUT      │ │ CAMERA      │ │ POSE         │ │ STYLE        │
│ BEATS  │ │ DETECT   │ │ MOTION      │ │ EXTRACTION   │ │ PROFILE      │
│        │ │          │ │ (Optical    │ │ (MediaPipe)  │ │ (VLM)        │
│librosa │ │PyScene   │ │  Flow)      │ │              │ │ Qwen3.6      │
└────────┘ └──────────┘ └─────────────┘ └──────────────┘ └──────────────┘
                                │               │                │
                                ▼               ▼                ▼
                     ┌──────────────────────────────────────────────┐
                     │   SKILL ARCHIVE (.storyline/skills/)        │
                     │   ├── SKILL.md (Director prompt)            │
                     │   ├── context.json (beats, cuts, motion)    │
                     │   └── reference_poses.json (33 landmarks)   │
                     └──────────────────────────────────────────────┘
```

#### 1a. Audio Beat Detection (`librosa`)
- Extracts audio via `ffmpeg` → `temp/extracted_audio.mp3`
- `librosa.beat.beat_track()` finds the BPM and exact beat timestamps
- These beats are later used to **snap video cuts to the rhythm**

#### 1b. Scene Cut Detection (`PySceneDetect`)
- Scans every frame of the video using `ContentDetector`
- Finds scene change timestamps (e.g., `[0.0, 2.3, 5.1, 8.0]`)
- The number of cuts determines how many shots you need to film

#### 1c. Camera Motion Analysis (Optical Flow — OpenCV)

Uses **Farneback dense optical flow** to detect camera movement:

```
Frame N          Frame N+1        Flow Vectors
┌──────────┐    ┌──────────┐    ┌──────────┐
│          │    │    →     │    │  → → →   │  = Pan Right
│    ○     │ →  │     ○    │    │  → → →   │
│          │    │          │    │  → → →   │
└──────────┘    └──────────┘    └──────────┘
```

- Samples consecutive frame pairs every 0.3s
- Computes dense optical flow using `cv2.calcOpticalFlowFarneback()`
- **Pan Detection:** Global average of flow vectors → direction
- **Zoom Detection:** Radial flow divergence from image center
- Classifies each segment: `static`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `zoom_in`, `zoom_out`
- Output: timeline of camera motions with timestamps and magnitudes

#### 1d. Reference Pose Extraction (MediaPipe)

Extracts **33 body landmarks** from each frame:

```
MediaPipe 33-Point Skeleton
        0 (nose)
       / \
     11   12 (shoulders)
     |     |
    13   14 (elbows)
     |     |
    15   16 (wrists)
       |
     23-24 (hips)
     |     |
    25   26 (knees)
     |     |
    27   28 (ankles)
```

- Samples frames every 0.1s
- Normalizes coordinates relative to **hip center** (translation-invariant)
- Stores as JSON: `[{time, landmarks[33][4], normalized[33][4]}, ...]`
- Saved to `reference_poses.json` in the Skill archive
- Used by the Hybrid Director in Step 2 for **DTW comparison**

#### 1e. Beat-Cut Correlation (Audio-Visual Sync)
- For each scene cut, finds the nearest beat timestamp
- Flags if cuts are rhythmically aligned (within 150ms)
- Feeds sync data into the VLM merge prompt for better style understanding

#### 1f. Style Profile Extraction (VLM — Scene-Aligned Batched Analysis)

Uses the VLM for **narrative-aware, scene-aligned** analysis:

```
69s video @ 0.3s intervals = ~232 frames
    │
    ▼
Align sampling to scene cuts (A1)
Group by scene → chunk into 3×3 batches
    │
    ├── Scene 1 Batch (0.0-2.3s): 3×3 grid + "Previously: N/A" → VLM → obs_1
    ├── Scene 2 Batch (2.3-5.1s): 3×3 grid + "Previously: obs_1" → VLM → obs_2  ← Rolling Context (A2)
    ├── Scene N Batch:            (blur-free frames selected) → VLM → obs_N       ← Blur Detection (A3)
    │
    ▼
MERGE STEP: All observations + beat-cut sync data → VLM → Final JSON profile
```

**Improvements over v2:**
- **Scene-aligned batching (A1):** Batches never cross scene cuts, improving VLM comprehension
- **Rolling context (A2):** Each batch sees a summary of the previous batch for narrative continuity
- **Blur detection (A3):** Blurry frames are replaced with sharper nearby alternatives
- **Beat-cut correlation (A4):** The merge step knows which transitions are beat-synced

**Output fields:** `video_type`, `narrative`, `clothing`, `setting`, `camera_angle`, `key_transition`, `recreation_tips`

#### 1g. Pose Interpolation
- After extraction, scans for gaps (frames where MediaPipe lost tracking)
- Fills gaps with linear interpolation between neighboring poses
- Marks interpolated frames with lower confidence for downstream DTW

#### 1h. Script & Caption Generation (VLM — Few-Shot)
- Uses few-shot style transfer prompting
- Generates a viral caption and hook script matching the extracted style

---

### Step 2: The Studio — Hybrid Director (CV + VLM)

The Studio uses a **dual-speed feedback loop** that combines fast computer vision with deep VLM analysis:

```
                         ┌──────────────────────────────┐
                         │      FAST LOOP (CPU)         │
                         │      Every frame (~10fps)    │
   Webcam Frame ────────►│                              │──► "Right hand 15% too low"
                         │  • MediaPipe Pose Tracking   │──► "You're 0.3s behind beat"
                         │  • DTW Pose Comparison       │──► "Pan right now!"
                         │  • Optical Flow Matching     │──► "🎯 Pose matches!"
                         └───────────┬──────────────────┘
                                     │
                                Every 3 seconds
                                     │
                         ┌───────────▼──────────────────┐
                         │      SLOW LOOP (GPU)         │
                         │      Every 3 seconds         │
                         │                              │──► "Change your shirt"
                         │  • Qwen3.6 VLM              │──► "Lighting too dark"
                         │  • Style/outfit/lighting     │──► "Perfect" → auto-record
                         └──────────────────────────────┘
```

**Why Hybrid?** Calling a 35B VLM on every webcam frame is too slow. The fast CV loop handles **spatial and temporal alignment** (pose matching, camera motion) at real-time speed, while the VLM handles **semantic understanding** (outfit, lighting, background) every few seconds.

#### Pose Comparison (DTW — Dynamic Time Warping)

```python
# How DTW works for pose matching:
Reference:  [pose_0, pose_1, pose_2, pose_3, ...]  (from TikTok)
User:       [pose_a, pose_b, pose_c, ...]           (from webcam)

DTW aligns them optimally even if the user is slightly faster/slower:
  Reference: |--0--|--1--|--2--|--3--|
  User:      |--a-----|--b--|--c--|
  DTW:          ↕       ↕      ↕        → distance = Σ deviations
```

- Compares 13 key joints (nose, shoulders, elbows, wrists, hips, knees, ankles)
- Reports per-joint deviations: *"right hand 15% too far left"*
- Reports temporal offset: *"You're 0.5s behind the beat"*

#### Scene-Aware Direction (Per-Shot Prompts)

The Director adapts its prompt based on the current shot:
- **Shot 1 (opening):** "Verify casual outfit, good lighting"
- **Shot 3 (transition):** "Hand covers camera — ready to reveal"
- **Shot 5 (reveal):** "Verify cosplay outfit matches reference"

#### Three Input Modes

1. **Pre-Flight Check** (recommended first): Static analysis of outfit + lighting before recording
2. **Upload Mode** (works everywhere): Upload pre-filmed clips, get **CV + VLM** review per clip
3. **Webcam Mode** (requires HTTPS): Real-time hybrid direction with auto-recording

---

### Step 3: Final Output (Render + Judge)

#### Beat-Synced Rendering

```
recorded_shots/     context.json
    │                    │
    ▼                    ▼
[shot_0.mp4]     cuts: [0.0, 2.3, 5.1, 8.0]
[shot_1.mp4]     beats: [0.48, 0.97, 1.45, ...]
[shot_2.mp4]     audio: temp/extracted_audio.mp3
    │                    │
    ▼                    ▼
┌─────────────────────────────────────┐
│ snap_cuts_to_beats()                │
│ Align cuts → nearest musical beat   │
│ (within 0.2s threshold)             │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│ Trim + Concatenate + Audio Overlay  │
│ → final_trend.mp4                   │
└─────────────────────────────────────┘
```

#### AI Judge
- Extracts a frame from the final video
- VLM scores 0–10 against the intended style profile
- Returns detailed critique

---

## 📁 Repository Structure

| File | Description |
|------|-------------|
| `app.py` | Main Gradio web application with 3-tab UI; orchestrates all modules |
| `analyzer.py` | Downloads videos, extracts audio, analyzes beats/cuts, **optical flow**, **MediaPipe poses**, and VLM style |
| `director.py` | **Hybrid Director**: `PoseTracker` (MediaPipe + DTW), `check_camera_motion` (optical flow), fast/slow feedback loops |
| `config.py` | **Centralized configuration** — model names, API URLs, timeouts via environment variables |
| `depth_estimator.py` | **Depth Anything V2** wrapper for monocular depth comparison (🧪 experimental, GPU) |
| `renderer.py` | Trims and stitches clips using `moviepy`, beat-synced cut alignment, audio overlay |
| `evaluator.py` | Extracts a frame from the final video and scores it against the style profile via VLM |
| `scriptwriter.py` | Generates a TikTok caption and hook script using few-shot style transfer |
| `skill_manager.py` | Saves/loads Skill archives, generates **per-scene director prompts** |
| `mcp_server.py` | MCP server for external AI agent integration |
| `Depth-Anything-V2/` | Cloned repo for depth estimation (🧪 not tracked in git) |

### Skill Archive Format

```
.storyline/skills/trend_reference_video/
├── SKILL.md                # YAML frontmatter + Director system prompt
├── context.json            # Beats, cuts, audio, camera_motion timeline
└── reference_poses.json    # MediaPipe 33-landmark poses @ 0.1s intervals
```

---

## 🧩 Architecture: Multi-Model on MI300X

The system demonstrates running **multiple AI models simultaneously** on the MI300X's 192GB VRAM:

```
┌───────────────────────────────────────────────────────────────┐
│                     AMD MI300X (192GB VRAM)                    │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Docker Container (ROCm + vLLM)                         │ │
│  │                                                          │ │
│  │  ┌─────────────────────┐   ┌────────────────────────┐   │ │
│  │  │ Qwen3.6-35B-A3B     │   │ Depth Anything V2      │   │ │
│  │  │ (VLM — ~70GB)       │   │ (Depth — ~1GB)         │   │ │
│  │  │ Port :8000           │   │ (Optional)              │   │ │
│  │  └─────────────────────┘   └────────────────────────┘   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              ▲                                │
│                              │ HTTP (localhost:8000)           │
│  ┌───────────────────────────┼──────────────────────────────┐ │
│  │  Host OS (VM)             │                              │ │
│  │                           │                              │ │
│  │  app.py (Gradio UI)    ◄──┘                              │ │
│  │  analyzer.py (Optical Flow, MediaPipe Pose — CPU)        │ │
│  │  director.py (PoseTracker, DTW, Camera Motion — CPU)     │ │
│  │  renderer.py (MoviePy — CPU)                             │ │
│  │                                                          │ │
│  │  Port :7860                                              │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

**Key Insight:** CV operations (MediaPipe, OpenCV optical flow, DTW) run on **CPU** for real-time speed. The VLM runs on **GPU** for semantic understanding. This split maximizes hardware utilization.

---

## ⚙️ Configuration (Environment Variables)

All model names and endpoints are configurable via `config.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRENDFLOW_VLLM_URL` | `http://localhost:8000/v1/chat/completions` | Main vLLM API endpoint |
| `TRENDFLOW_DIRECTOR_VLLM_URL` | Same as above | Separate endpoint for fast director model |
| `TRENDFLOW_ANALYSIS_MODEL` | `Qwen/Qwen3.6-35B-A3B` | Model for trend analysis (72B recommended) |
| `TRENDFLOW_DIRECTOR_MODEL` | `Qwen/Qwen3.6-35B-A3B` | Model for real-time directing (12B recommended) |
| `TRENDFLOW_DIRECTOR_VLM_INTERVAL` | `3.0` | Seconds between VLM director checks |

**Optional Dual-Model Strategy (MI300X):**

Two vLLM servers must share the same GPU memory. If the first server starts with a high `--gpu-memory-utilization` value, the second server can fail with `Free memory ... is less than desired GPU memory utilization`. Check free VRAM first, then start each server with explicit memory caps.

```bash
# Check current GPU memory usage
rocm-smi

# Terminal 1: Main model for analysis (port 8000)
vllm serve Qwen/Qwen3.6-35B-A3B \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.65 \
  --max-model-len 49152

# Terminal 2: Fast model for directing (port 8001)
vllm serve mistralai/Pixtral-12B-2409 \
  --port 8001 \
  --gpu-memory-utilization 0.20 \
  --max-model-len 16384

# Set env vars
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_VLLM_URL="http://localhost:8000/v1/chat/completions"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://localhost:8001/v1/chat/completions"
```

If Pixtral fails with a safetensors or tokenizer-format error, relaunch it with:

```bash
vllm serve mistralai/Pixtral-12B-2409 \
  --port 8001 \
  --tokenizer-mode mistral \
  --load-format mistral \
  --limit-mm-per-prompt image=4 \
  --gpu-memory-utilization 0.20 \
  --max-model-len 16384
```

If Pixtral still cannot start, stop the first vLLM server or relaunch it with a lower `--gpu-memory-utilization` value before starting the second one.

---

## 🛠️ Environment & Setup

Use **Python 3.12**. The pinned MediaPipe stack in `requirements.txt` uses the legacy `mediapipe.solutions.pose` API, which is required for real-time pose tracking and reference pose extraction. Do not use Python 3.13 for this app.

### Quick Setup

Run the setup script from the repo root:

```bash
./setup.sh
```

The script creates or reuses `.conda/trendsync-py312`, installs `ffmpeg`, installs `requirements.txt`, runs `pip check`, and verifies `mediapipe.solutions.pose`.

### 1. Clone The Repo

```bash
git clone https://github.com/namprice227/trendsync
cd trendsync
```

### 2. Create The Conda Environment

Create the environment inside the project so it is easy to find and reproduce:

```bash
conda create -y -p "$PWD/.conda/trendsync-py312" python=3.12 pip
conda activate "$PWD/.conda/trendsync-py312"
```

If your shell has not been initialized for `conda`, use:

```bash
source /home/nam/miniconda3/bin/activate "$PWD/.conda/trendsync-py312"
```

### 3. Install Runtime Tools

Install `ffmpeg` in the conda environment. It is used by `yt-dlp`, MoviePy, and the audio extraction path.

```bash
conda install -y -c conda-forge ffmpeg
```

The analyzer also falls back to the `imageio-ffmpeg` binary from Python packages if a system `ffmpeg` is not available, but the conda `ffmpeg` package is still recommended.

### 4. Install Python Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

Expected result:

```text
No broken requirements found.
```

### 5. Verify MediaPipe Pose Works

Run this quick check before launching the app:

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

Expected output includes:

```text
mediapipe 0.10.14
has solutions: True
has pose: True
pose constructor ok
```

### 6. Run The App

Normal run:

```bash
MPLCONFIGDIR=/tmp/mpl python app.py
```

The UI is available at:

- Local: `http://127.0.0.1:7860`
- Remote VM: `http://<VM-IP>:7860`
- Public Gradio share URL: printed in the terminal when `share=True`

If port `7860` is already busy, launch on another port:

```bash
MPLCONFIGDIR=/tmp/mpl python -c "import app; app.launch_demo(server_name='127.0.0.1', server_port=7861, share=False)"
```

### 7. Optional: Run The VLM Server

The app can run without a local VLM server. VLM calls fall back to mock responses, while CPU features like MediaPipe pose tracking, optical flow, beat detection, and rendering still work.

For full VLM analysis/directing on an AMD GPU, start vLLM separately:

```bash
vllm serve Qwen/Qwen3.6-35B-A3B \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.65 \
  --max-model-len 49152
```

Then point the app at it if needed:

```bash
export TRENDFLOW_VLLM_URL="http://localhost:8000/v1/chat/completions"
export TRENDFLOW_ANALYSIS_MODEL="Qwen/Qwen3.6-35B-A3B"
export TRENDFLOW_DIRECTOR_MODEL="Qwen/Qwen3.6-35B-A3B"
```

For a dual-model setup, start a second server only if enough GPU memory is free. Your vLLM error `Free memory ... is less than desired GPU memory utilization` means another process already reserved most of the GPU.

```bash
rocm-smi

vllm serve mistralai/Pixtral-12B-2409 \
  --port 8001 \
  --gpu-memory-utilization 0.20 \
  --max-model-len 16384
```

If Pixtral fails with a safetensors or tokenizer-format error, add the Mistral loader flags:

```bash
vllm serve mistralai/Pixtral-12B-2409 \
  --port 8001 \
  --tokenizer-mode mistral \
  --load-format mistral \
  --limit-mm-per-prompt image=4 \
  --gpu-memory-utilization 0.20 \
  --max-model-len 16384
```

Then point the director at it:

```bash
export TRENDFLOW_DIRECTOR_VLLM_URL="http://localhost:8001/v1/chat/completions"
export TRENDFLOW_DIRECTOR_MODEL="mistralai/Pixtral-12B-2409"
```

If the first vLLM server was started with `--gpu-memory-utilization 0.9` or higher, stop it or relaunch it with a lower cap before starting Pixtral.

### 8. Optional: Depth Anything V2

Depth estimation is optional. Clone the repo only if you want experimental depth feedback:

```bash
git clone --depth 1 https://github.com/DepthAnything/Depth-Anything-V2.git
```

---

## 🕹️ Using the Application

### ① Analyze Trend
1. Paste a TikTok URL → Click **🔍 Analyze Trend**
2. Wait for analysis (2-5 minutes for long videos with VLM)
3. Review results:
   - **Video Type** — Transition, dance, tutorial, etc.
   - **Narrative** — What happens start-to-end
   - **AI Style Guide** — Clothing, setting, camera framing
   - **Camera Motion Profile** — Pan/zoom/static breakdown
   - **Pose Data** — Number of reference poses extracted
   - **Generated Script & Caption**

### ② The Studio
1. **🔍 Pre-Flight Check** — verify outfit + lighting before recording
2. **Upload clips** or use webcam (HTTPS only)
3. See **hybrid feedback**:
   - ⚡ **CV (real-time):** Pose alignment (DTW %), camera motion matching
   - 🧠 **AI Director (style, scene-aware):** Per-shot outfit, lighting, composition
4. Auto-records when VLM says "Perfect"

### ③ Final Output
1. **🎬 Assemble Final Video** — beat-synced rendering
2. **⭐ Judge My Video** — AI score 0–10 + critique

---

## 🔧 Key Technical Details

### VLM Configuration (Qwen3.6)
- **Thinking Mode Disabled:** `"chat_template_kwargs": {"enable_thinking": False}`
- **Think Tag Stripping:** Post-processing strips `<think>...</think>` blocks
- **Timeouts:** Analyzer (120s), Director (30s), Evaluator (60s), Scriptwriter (60s)

### CV Pipeline (CPU)
- **MediaPipe Pose:** Pinned to `mediapipe==0.10.14` on Python 3.12, using the legacy `mp.solutions.pose` API with model complexity 1
- **Optical Flow:** Farneback, downscaled to 320×240 for speed
- **DTW:** `dtaidistance` library with fast C implementation and pruning

### Graceful Fallbacks
Every module works without GPU:
- **VLM calls** → Mock responses
- **MediaPipe** → Required for pose features; setup verifies `mp.solutions.pose` before running
- **Depth Anything** → Skipped if no GPU or weights

---

## 📦 Dependencies

```
gradio              # Web UI framework
yt-dlp              # TikTok/YouTube video downloader
librosa             # Audio analysis (BPM, beat detection)
scenedetect         # Video scene cut detection
moviepy             # Video editing (trim, concat, audio overlay)
requests            # HTTP client for vLLM API
opencv-python       # Frame extraction and optical flow
opencv-contrib-python  # Extra OpenCV modules used by the pinned stack
PyYAML              # Skill archive serialization
fastmcp             # MCP server for agent integration
mediapipe==0.10.14  # Real-time pose tracking (CPU, Python 3.12)
dtaidistance        # Dynamic Time Warping for pose comparison
numpy               # Numerical operations
protobuf            # MediaPipe-compatible protobuf runtime
jax / jaxlib        # MediaPipe runtime dependencies
```

---

## 📚 References & Open-Source Libraries

| Library | Usage in TrendFlow AI |
|---------|----------------------|
| [MediaPipe](https://google.github.io/mediapipe/) | Real-time 33-point body pose tracking (CPU, 30fps) |
| [dtaidistance](https://github.com/wannesm/dtaidistance) | DTW algorithm for comparing pose sequences |
| [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) | Monocular depth estimation for scene matching |
| [vLLM](https://github.com/vllm-project/vllm) | High-throughput LLM/VLM serving with PagedAttention |
| [Qwen3](https://huggingface.co/Qwen) | Vision-Language Model for style analysis and directing |
| [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | Skill archiving format and beat-syncing inspiration |
| [AMD ROCm](https://rocm.docs.amd.com/) | GPU compute platform for MI300X |

---

## 🧠 Advanced: AMD Cloud Training

### Fine-Tuning the Director VLM (QLoRA)
Fine-tune a 7B model (e.g., `Qwen2.5-VL-7B`) for precise directorial commands:
- **Dataset:** ~500 image+command pairs in ShareGPT format
- **Training:** `SFTTrainer` with LoRA adapters, 3-4 epochs on ROCm
- **Deploy:** `vllm serve ... --enable-lora --lora-modules director=./weights`

### Training a Virality Reward Model
Custom regression model scoring videos by engagement:
- **Dataset:** ~400 viral/flop TikToks, normalized engagement 0.0–1.0
- **Training:** Keyframes → CLIP embeddings → Linear head → MSE loss
- **Deploy:** Update `evaluator.py` to use the custom `.pt` model

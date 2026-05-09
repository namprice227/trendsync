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

#### 1e. Style Profile Extraction (VLM — Batched 3×3 Analysis)

Uses the **Qwen3.6-35B-A3B** vision-language model for narrative-aware analysis:

```
69s video @ 0.3s intervals = ~232 frames
    │
    ▼
Split into batches of 9 → 26 batches
    │
    ├── Batch  1/26 (beginning): 3×3 grid → VLM → "Person in casual clothes..."
    ├── Batch 14/26 (middle):    3×3 grid → VLM → "Hand covers camera, transition..."
    ├── Batch 26/26 (end):       3×3 grid → VLM → "Full cosplay revealed..."
    │
    ▼
MERGE STEP: All 26 observations → VLM → Final JSON profile
```

**Output fields:** `video_type`, `narrative`, `clothing`, `setting`, `camera_angle`, `key_transition`, `recreation_tips`

#### 1f. Script & Caption Generation (VLM — Few-Shot)
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

#### Two Input Modes

1. **Upload Mode** (works everywhere): Upload pre-filmed clips, get AI review per clip
2. **Webcam Mode** (requires HTTPS): Real-time hybrid direction with auto-recording

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
| `depth_estimator.py` | **Depth Anything V2** wrapper for monocular depth comparison (optional, GPU) |
| `renderer.py` | Trims and stitches clips using `moviepy`, beat-synced cut alignment, audio overlay |
| `evaluator.py` | Extracts a frame from the final video and scores it against the style profile via VLM |
| `scriptwriter.py` | Generates a TikTok caption and hook script using few-shot style transfer |
| `skill_manager.py` | Saves/loads Skill archives (style + context + **reference poses** + **camera motion**) |
| `mcp_server.py` | MCP server for external AI agent integration |
| `Depth-Anything-V2/` | Cloned repo for depth estimation (not tracked in git) |

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

## 🛠️ Environment & Setup

### Option A: AMD Cloud GPU Deployment (Recommended)

**1. Start the ROCm Docker Container:**

```bash
docker run -it --network=host --device=/dev/kfd --device=/dev/dri \
  --group-add=video --ipc=host --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  rocm/vllm-dev:latest
```

**2. Inside Docker — Start vLLM:**

```bash
vllm serve Qwen/Qwen3.6-35B-A3B \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 32768
```

> **Note:** `Qwen/Qwen3.6-35B-A3B` is a gated model. Run `huggingface-cli login` and accept the license on Hugging Face first.

**3. On the Host VM — Install dependencies and run:**

```bash
apt-get update && apt-get install ffmpeg libsm6 libxext6 -y

git clone https://github.com/namprice227/trendsync
cd trendsync

# Clone Depth Anything V2 (optional, for depth estimation)
git clone --depth 1 https://github.com/DepthAnything/Depth-Anything-V2.git

pip install -r requirements.txt
python app.py
```

**4. Access the UI:**
- Local: `http://<VM-IP>:7860`
- Public share link: shown in terminal (via Gradio `share=True`)

### Option B: Local Testing (Without Cloud GPU)

All VLM calls **fall back to mock responses** when no vLLM server is running. CV features (pose, optical flow) work locally.

```bash
conda create -n trendsync python=3.12 -y
conda activate trendsync
conda install -c conda-forge ffmpeg -y
pip install -r requirements.txt
python app.py
```

> **Note:** MediaPipe requires Python 3.9–3.12. Use Python 3.12 for full feature support.

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
1. **Upload clips** (recommended) or use webcam (HTTPS only)
2. See **hybrid feedback**:
   - ⚡ **CV (real-time):** Pose alignment, camera motion matching
   - 🧠 **AI Director (style):** Outfit, lighting, composition
3. Auto-records when VLM says "Perfect"

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
- **MediaPipe Pose:** Model complexity 0 (fastest) for real-time, complexity 1 for reference extraction
- **Optical Flow:** Farneback, downscaled to 320×240 for speed
- **DTW:** `dtaidistance` library with fast C implementation and pruning

### Graceful Fallbacks
Every module works without GPU:
- **VLM calls** → Mock responses
- **MediaPipe** → Skipped if not installed
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
opencv-python-headless  # Frame extraction, optical flow, encoding
PyYAML              # Skill archive serialization
fastmcp             # MCP server for agent integration
mediapipe           # Real-time pose tracking (CPU)
dtaidistance        # Dynamic Time Warping for pose comparison
numpy               # Numerical operations
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

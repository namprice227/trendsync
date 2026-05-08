# 🎬 TrendFlow AI: The Autonomous TikTok Director & Editor

TrendFlow AI is an end-to-end agentic pipeline that watches viral TikTok trends, reverse-engineers their editing math, and acts as a real-time, on-set AI director to help you film and edit your own perfectly synced version.

Built for the [AMD Developer Hackathon](https://lablab.ai/ai-hackathons/amd-developer), optimized for **AMD MI300X** with ROCm.

## 📖 The User Experience

1. **Paste Link:** Provide a link to a trending TikTok or Reel.
2. **AI Deconstruction:** The system downloads the video, extracts audio, detects beats and cuts, extracts a visual style profile (clothing, setting, camera angle), and archives everything as a reusable **Skill**.
3. **AI Script Generation:** A Few-Shot scriptwriter generates a viral caption and hook based on the extracted style.
4. **Live Directing:** Turn on your webcam. The AI VLM analyzes the live feed and gives real-time text feedback (e.g., *"Step back into the frame"*, *"Change your outfit"*, *"Perfect"*). The system prompt is loaded dynamically from the archived Skill.
5. **Auto-Assemble:** Once all shots are captured, the AI stitches them together with **beat-synced cuts** aligned to the original audio.
6. **AI Judge:** After rendering, click "Judge My Video" — the AI evaluates your final video against the intended style and gives a score out of 10 with a critique.

## 📁 Repository Structure

| File | Description |
|------|-------------|
| `app.py` | Main Gradio web application; orchestrates all modules. |
| `analyzer.py` | Downloads videos via `yt-dlp`, extracts audio, analyzes beats/cuts with `librosa` and `scenedetect`, and extracts a visual style profile via VLM. |
| `director.py` | Sends live webcam frames to the vLLM server for real-time directing feedback; handles video recording via OpenCV. |
| `renderer.py` | Trims and stitches clips using `moviepy`, applies **beat-synced** cut alignment, and overlays the original audio. |
| `evaluator.py` | Extracts a frame from the final video and scores it against the style profile via VLM. |
| `skill_manager.py` | Saves/loads editing workflows as reusable **Skill** archives (`.storyline/skills/`), inspired by [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline). |
| `scriptwriter.py` | Generates a TikTok caption and hook script using Few-Shot style transfer via VLM. |
| `mcp_server.py` | Exposes the pipeline as an MCP (Model Context Protocol) server, allowing external AI agents to control it. |
| `requirements.txt` | Python package dependencies. |

### Skill Archive Format (`.storyline/skills/`)

When you analyze a trend, the system saves a **Skill** — a self-contained, reusable editing recipe:

```
.storyline/skills/trend_reference_video/
├── SKILL.md          # YAML frontmatter (style metadata) + Markdown (Director system prompt)
└── context.json      # Beats, cuts, audio path, reference video path
```

## 🛠️ Environment & Setup

### Option A: AMD Cloud GPU Deployment (Recommended)

This project is optimized for an AMD MI300X instance using ROCm with `vLLM` for the vision encoder.

1. **Start the ROCm Docker Container:**

   ```bash
   docker run -it --network=host --device=/dev/kfd --device=/dev/dri \
     --group-add=video --ipc=host --cap-add=SYS_PTRACE \
     --security-opt seccomp=unconfined \
     rocm/vllm-dev:latest
   ```

2. **Install System Dependencies inside Docker:**

   ```bash
   apt-get update && apt-get install ffmpeg libsm6 libxext6 -y
   ```

3. **Install Python Requirements:**

   ```bash
   pip install -r requirements.txt
   ```

### Option B: Local Testing (Without Cloud GPU)

The application automatically falls back to mocked VLM responses when no vLLM server is running, so you can test the full UI locally.

1. **Create and Activate Conda Environment:**
   ```bash
   conda create -n trendsync python=3.10 -y
   conda activate trendsync
   ```

2. **Install System & Python Requirements:**
   ```bash
   conda install -c conda-forge ffmpeg -y
   pip install -r requirements.txt
   ```

## 🏃‍♂️ How to Run

### 1. Start the vLLM Engine (Cloud GPU only)

```bash
vllm serve Qwen/Qwen3.5-VL-27B-Instruct \
  --tensor-parallel-size 1 \
  --mm-encoder-tp-mode data \
  --max-model-len 32768
```

### 2. Start the Gradio UI
In a separate terminal:

```bash
python app.py
```

Access the UI at **http://0.0.0.0:7860**

### 3. (Optional) Start the MCP Server
To expose the pipeline to external AI agents:

```bash
python mcp_server.py
```

## 🕹️ Using the Application

The web interface has three tabs:

### Step 1: Trend Analyzer
1. Paste the URL of a TikTok or YouTube Shorts video.
2. Click **Analyze Trend**.
3. The system downloads the video, extracts audio, detects beats/cuts, generates a style profile, and saves a reusable **Skill** archive.
4. You'll see the **AI Style Guide** (what to wear, where to shoot, camera framing) and a **Generated Script & Caption** for your video.

### Step 2: The Studio
1. Ensure your webcam is connected.
2. The AI Director analyzes your live feed and displays real-time feedback based on the extracted style from the Skill archive.
3. When the AI determines the framing is "Perfect," it automatically starts recording for the exact duration needed for the current shot.
4. Wait for all required shots to be captured.

### Step 3: Final Output
1. Click **Assemble Final Video** — the renderer stitches clips together with beat-synced cuts and overlays the original audio.
2. Click **Judge My Video** — the AI evaluator scores your final video out of 10 with a detailed critique.

## 🧠 Advanced: AMD Cloud Training (Hackathon Edge)

If you are using an AMD Cloud Instance (e.g., MI300X with ROCm), you can train and fine-tune your own models to drastically improve the AI Director and Evaluator.

### Training Environment Setup
1. **Start the PyTorch/ROCm Container:**
   ```bash
   docker run -it --network=host --device=/dev/kfd --device=/dev/dri \
     --group-add=video --ipc=host --cap-add=SYS_PTRACE \
     --security-opt seccomp=unconfined \
     rocm/pytorch:latest
   ```
2. **Install Training Libraries:**
   ```bash
   pip install transformers accelerate peft trl bitsandbytes datasets
   ```
3. **Authenticate with Hugging Face:** `huggingface-cli login`

### Fine-Tuning the Director VLM (QLoRA)
Fine-tune a smaller 7B model (like `Qwen2.5-VL-7B`) to output precise directorial commands.
* **Dataset:** Create ~500 image+command pairs in JSONL/ShareGPT format.
* **Training:** Use `SFTTrainer` with `peft` LoRA adapters for 3-4 epochs on ROCm.
* **Deployment:** Load LoRA weights directly into vLLM:
  ```bash
  vllm serve Qwen/Qwen2.5-VL-7B-Instruct --enable-lora --lora-modules director=./my_lora_weights
  ```

### Training a Virality Reward Model
Train a custom regression model to score videos based on real engagement data.
* **Dataset:** Collect ~200 viral and ~200 flop TikToks. Normalize engagement to 0.0–1.0.
* **Training:** Extract keyframes → CLIP embeddings → Linear regression head → MSE loss.
* **Deployment:** Update `evaluator.py` to use the custom `.pt` model instead of the VLM API.

## 📚 Acknowledgments

* [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) — Skill archiving format and beat-syncing architecture inspiration.
* [AMD ROCm](https://rocm.docs.amd.com/) — GPU compute platform.
* [vLLM](https://github.com/vllm-project/vllm) — High-throughput LLM serving engine.

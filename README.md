# 🎬 TrendFlow AI: The Autonomous TikTok Director & Editor

TrendFlow AI is an end-to-end agentic pipeline that watches viral TikTok trends, reverse-engineers their editing math, and acts as a real-time, on-set director to help you film and edit your own perfectly synced version.

## 📖 The User Experience

1. **Paste Link:** Provide a link to a trending TikTok or Reel.
2. **AI Deconstruction:** The system breaks the video down into a shot list, audio beats, and cut timings, saving them to a JSON profile.
3. **Live Directing:** Turn on your webcam. The AI Vision-Language Model (VLM) analyzes the live feed and gives real-time verbal/text feedback (e.g., *"Step back into the frame"*, *"Lighting is too dark"*, *"Perfect"*).
4. **Auto-Assemble:** Once all shots are captured based on the exact durations of the original trend, the AI seamlessly stitches them together, aligned perfectly to the original trend's audio.

## 📁 Repository Structure

* `app.py`: The main Gradio web application that ties all components together.
* `analyzer.py`: Downloads videos via `yt-dlp`, extracts audio, and analyzes beats/cuts using `librosa` and `scenedetect`.
* `director.py`: Interfaces with the local vLLM server using the OpenAI-compatible API to get frame-by-frame directing feedback and handles video recording using OpenCV.
* `renderer.py`: Trims and stitches the user's recorded clips together using `moviepy`, overlaying the trend's original audio track.
* `requirements.txt`: Python package dependencies.

## 🛠️ Environment & Setup (AMD ROCm / MI300X)

This project is optimized for an AMD MI300X instance using ROCm, taking advantage of `vLLM`'s batch-level Data Parallelism mode for the vision encoder.

### Option A: Cloud GPU Deployment (Recommended for full vLLM)

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
If you are developing locally and just want to test the Gradio UI without running the massive vLLM model (the application will automatically fall back to mocked responses if vLLM isn't found), you can use Conda:

1. **Create and Activate Conda Environment:**
   ```bash
   conda create -n trendsync python=3.10 -y
   conda activate trendsync
   ```

2. **Install System & Python Requirements:**
   You will need `ffmpeg` for video/audio processing. Conda can install this for you:
   ```bash
   conda install -c conda-forge ffmpeg -y
   pip install -r requirements.txt
   ```

## 🏃‍♂️ How to Run the App

You will need two terminal windows running inside your environment.

### 1. Start the vLLM Engine
Start the local VLM server. We use `Qwen/Qwen3.5-VL-27B-Instruct` for fast real-time inference.

```bash
vllm serve Qwen/Qwen3.5-VL-27B-Instruct \
  --tensor-parallel-size 1 \
  --mm-encoder-tp-mode data \
  --max-model-len 32768
```

### 2. Start the Backend and UI
In a separate terminal, launch the Gradio application.

```bash
python app.py
```

*Access the UI via your browser at http://0.0.0.0:7860.*

## 🕹️ Using the Application

The web interface is divided into three main tabs:

### Step 1: Trend Analyzer
1. Navigate to the **Step 1: Trend Analyzer** tab.
2. Paste the URL of a TikTok or YouTube Shorts video.
3. Click **Analyze Trend**. The system will download the video, extract the audio, detect cuts, and generate the `trend_profile.json` displayed on the right.

### Step 2: The Studio
1. Navigate to the **Step 2: The Studio** tab.
2. Ensure your webcam is connected and recognized by OpenCV (`cv2.VideoCapture(0)`). Note: If you are running the backend on a remote server, the server itself needs access to the video device.
3. The AI Director will analyze the live feed continuously and display feedback below the camera feed.
4. When the AI determines the framing is "Perfect," it will automatically start recording for the exact duration needed for the current shot.
5. Wait for the status to show that all required shots have been captured.

### Step 3: Final Output
1. Navigate to the **Step 3: Final Output** tab.
2. Click **Assemble Final Video**.
3. The system will trim the clips, stitch them together, and apply the original audio. The final playable video will appear on the screen!

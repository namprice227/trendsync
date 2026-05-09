import os
import json
import librosa
from scenedetect import detect, ContentDetector
import yt_dlp
import subprocess
import cv2
import base64
from skill_manager import save_skill

def download_video(url: str, output_dir: str = "temp") -> str:
    """
    Downloads a video from a given URL using yt-dlp.
    Returns the path to the downloaded video.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Clean up old files to force fresh download
    for old_file in ['reference_video.mp4', 'reference_video.webm', 'extracted_audio.mp3']:
        old_path = os.path.join(output_dir, old_file)
        if os.path.exists(old_path):
            os.remove(old_path)
            print(f"Removed old file: {old_path}")
    
    outtmpl = os.path.join(output_dir, 'reference_video.%(ext)s')

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': outtmpl,
        'noplaylist': True,
    }

    print(f"Downloading video from {url}...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info_dict)

    print(f"Downloaded video to {filename}")
    return filename

def extract_audio(video_path: str, output_path: str) -> str:
    """
    Extracts audio from video using ffmpeg.
    """
    print(f"Extracting audio to {output_path}...")
    command = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def detect_audio_beats(audio_path: str):
    """
    Uses librosa to detect bpm and major beat timestamps.
    """
    print("Analyzing audio beats...")
    y, sr = librosa.load(audio_path)
    bpm, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Handle bpm arrays from newer librosa versions
    bpm_val = float(bpm[0]) if isinstance(bpm, (list, tuple)) or (hasattr(bpm, 'ndim') and bpm.ndim > 0) else float(bpm)
    return bpm_val, beat_times.tolist()

def detect_video_cuts(video_path: str):
    """
    Uses PySceneDetect to find cuts.
    """
    print("Analyzing video cuts...")
    scene_list = detect(video_path, ContentDetector())
    cuts = []

    # Scene list contains tuples of (start_time, end_time) FrameTimecodes
    for i, scene in enumerate(scene_list):
        if i == 0:
            cuts.append(0.0)
        else:
            cuts.append(scene[0].get_seconds())

    # Include the end of the last scene if there are scenes
    if scene_list:
        cuts.append(scene_list[-1][1].get_seconds())

    return cuts

import requests
import numpy as np
from config import VLLM_API_URL, ANALYSIS_MODEL, ANALYSIS_TIMEOUT

# ============================================================
# OPTICAL FLOW — Camera Motion Analysis
# ============================================================

def analyze_camera_motion(video_path: str, sample_interval: float = 0.3):
    """
    Analyzes camera motion throughout the video using Farneback optical flow.
    Returns a timeline of camera motion events:
      [{"time": 0.0, "motion": "static", "magnitude": 0.1}, ...]
    
    Motion types: static, pan_left, pan_right, pan_up, pan_down, zoom_in, zoom_out, complex
    """
    print("Analyzing camera motion (optical flow)...")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    ret, prev_frame = cap.read()
    if not ret:
        cap.release()
        return []
    
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.resize(prev_gray, (320, 240))  # Downscale for speed
    
    h, w = prev_gray.shape
    center_x, center_y = w / 2, h / 2
    y_grid, x_grid = np.indices((h, w))
    dx_from_center = (x_grid - center_x).astype(np.float32)
    dy_from_center = (y_grid - center_y).astype(np.float32)
    
    # Thresholds for motion classification
    PAN_THRESHOLD = 1.5
    ZOOM_THRESHOLD = 50.0
    
    motion_timeline = []
    current_time = sample_interval  # Skip first frame
    
    while current_time < duration:
        frame_idx = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 240))
        
        # Compute dense optical flow
        flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        fx, fy = flow[..., 0], flow[..., 1]
        
        # Global average for pan detection
        mean_dx = float(np.mean(fx))
        mean_dy = float(np.mean(fy))
        magnitude = float(np.sqrt(mean_dx**2 + mean_dy**2))
        
        # Radial flow for zoom detection
        radial_flow = float(np.mean(fx * dx_from_center + fy * dy_from_center))
        
        # Classify motion
        if abs(radial_flow) > ZOOM_THRESHOLD:
            motion = "zoom_in" if radial_flow < 0 else "zoom_out"
        elif magnitude > PAN_THRESHOLD:
            if abs(mean_dx) > abs(mean_dy):
                motion = "pan_right" if mean_dx > 0 else "pan_left"
            else:
                motion = "pan_down" if mean_dy > 0 else "pan_up"
        else:
            motion = "static"
        
        motion_timeline.append({
            "time": round(current_time, 2),
            "motion": motion,
            "magnitude": round(magnitude, 2)
        })
        
        prev_gray = gray
        current_time += sample_interval
    
    cap.release()
    
    # Summarize dominant motions
    motion_counts = {}
    for entry in motion_timeline:
        m = entry["motion"]
        motion_counts[m] = motion_counts.get(m, 0) + 1
    
    print(f"Camera motion analysis complete: {len(motion_timeline)} segments analyzed")
    print(f"  Motion summary: {motion_counts}")
    return motion_timeline

# ============================================================
# POSE EXTRACTION — MediaPipe Reference Poses
# ============================================================

def extract_reference_poses(video_path: str, sample_interval: float = 0.1):
    """
    Extracts body pose landmarks from the reference video using MediaPipe.
    Returns a list of pose snapshots: [{"time": 0.0, "landmarks": [...], "normalized": [...]}, ...]
    Each landmark has (x, y, z, visibility) for 33 body points.
    
    Falls back gracefully if MediaPipe is not installed.
    """
    try:
        import mediapipe as mp
    except ImportError:
        print("MediaPipe not installed — skipping pose extraction. Install with: pip install mediapipe")
        return []
    
    print("Extracting reference poses (MediaPipe)...")
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=True,
        model_complexity=1,
        min_detection_confidence=0.5
    )
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    pose_timeline = []
    current_time = 0.0
    
    while current_time < duration:
        frame_idx = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break
        
        # MediaPipe expects RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)
        
        if results.pose_landmarks:
            landmarks = []
            for lm in results.pose_landmarks.landmark:
                landmarks.append([lm.x, lm.y, lm.z, lm.visibility])
            
            # Normalize relative to hip center (landmark 23=left hip, 24=right hip)
            hip_x = (landmarks[23][0] + landmarks[24][0]) / 2
            hip_y = (landmarks[23][1] + landmarks[24][1]) / 2
            hip_z = (landmarks[23][2] + landmarks[24][2]) / 2
            
            normalized = []
            for lm in landmarks:
                normalized.append([
                    lm[0] - hip_x,
                    lm[1] - hip_y,
                    lm[2] - hip_z,
                    lm[3]  # visibility stays as-is
                ])
            
            pose_timeline.append({
                "time": round(current_time, 2),
                "landmarks": landmarks,
                "normalized": normalized
            })
        
        current_time += sample_interval
    
    cap.release()
    pose.close()
    
    print(f"Pose extraction complete: {len(pose_timeline)} poses extracted from {duration:.1f}s video")
    return pose_timeline

def encode_image_base64(frame):
    """Encodes a cv2 image frame to base64 string."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')

def is_blurry(frame, threshold: float = 100.0) -> bool:
    """Checks if a frame is too blurry using Laplacian variance."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var() < threshold

def sample_frames(video_path: str, interval: float = 0.3, cuts: list = None):
    """
    Samples frames from the video. If cuts are provided, aligns sampling
    to scene boundaries (A1: scene-cut-aligned batching). Skips blurry frames (A3).
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    frames = []
    blur_replaced = 0

    # Build sample times — aligned to scene cuts if available
    if cuts and len(cuts) >= 2:
        sample_times = []
        for i in range(len(cuts) - 1):
            scene_start, scene_end = cuts[i], cuts[i + 1] if i + 1 < len(cuts) else duration
            t = scene_start
            while t < scene_end:
                sample_times.append(t)
                t += interval
        # Add samples after the last cut
        t = cuts[-1]
        while t < duration:
            sample_times.append(t)
            t += interval
    else:
        sample_times = []
        t = 0.0
        while t < duration:
            sample_times.append(t)
            t += interval

    for current_time in sample_times:
        frame_idx = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # Blur detection: try nearby frames if blurry
        if is_blurry(frame):
            best_frame = frame
            best_var = cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
            for offset in [-2, -1, 1, 2]:
                alt_idx = max(0, frame_idx + offset)
                cap.set(cv2.CAP_PROP_POS_FRAMES, alt_idx)
                ret2, alt_frame = cap.read()
                if ret2:
                    alt_var = cv2.Laplacian(cv2.cvtColor(alt_frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
                    if alt_var > best_var:
                        best_frame = alt_frame
                        best_var = alt_var
            if best_var > cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var():
                blur_replaced += 1
            frame = best_frame

        frames.append((current_time, frame))
    
    cap.release()
    mode = "scene-aligned" if (cuts and len(cuts) >= 2) else f"{interval}s intervals"
    print(f"Sampled {len(frames)} frames ({mode}, {duration:.1f}s video, {blur_replaced} blur-replaced)")
    return frames

def create_contact_sheet(frames: list, thumb_width: int = 320, cols: int = 3):
    """
    Arranges sampled frames into a 3x3 grid contact sheet image.
    Returns a single image containing all frames in a grid.
    """
    if not frames:
        return None
    
    # Resize all frames to uniform thumbnail size
    thumbnails = []
    for _, frame in frames:
        h, w = frame.shape[:2]
        thumb_height = int(thumb_width * h / w)
        thumb = cv2.resize(frame, (thumb_width, thumb_height))
        thumbnails.append(thumb)
    
    # All thumbs should have same height (use the first one's height)
    thumb_h = thumbnails[0].shape[0]
    
    # Arrange into grid
    rows_needed = (len(thumbnails) + cols - 1) // cols
    # Pad with black frames if needed
    while len(thumbnails) % cols != 0:
        thumbnails.append(np.zeros((thumb_h, thumb_width, 3), dtype=np.uint8))
    
    grid_rows = []
    for r in range(rows_needed):
        row_thumbs = thumbnails[r * cols : (r + 1) * cols]
        grid_rows.append(np.hstack(row_thumbs))
    
    contact_sheet = np.vstack(grid_rows)
    return contact_sheet

def _analyze_batch(base64_image: str, batch_num: int, total_batches: int, 
                   num_frames: int, time_range: str, model_name: str,
                   previous_context: str = None) -> str:
    """
    Sends a single 3x3 contact sheet batch to the VLM.
    Includes rolling context from the previous batch for narrative continuity.
    Returns the raw text observation from the model.
    """
    position = "beginning" if batch_num <= total_batches * 0.33 else ("middle" if batch_num <= total_batches * 0.66 else "end")
    
    context_line = ""
    if previous_context:
        # Truncate to ~200 chars to save tokens
        prev_summary = previous_context[:200]
        context_line = f"\nPreviously in this video: {prev_summary}\nNow describe what happens NEXT.\n"

    system_prompt = (
        "You are an expert TikTok trend analyst studying viral video patterns. "
        f"This is batch {batch_num}/{total_batches} (the {position}) of a TikTok video. "
        f"The image is a 3x3 grid of {num_frames} frames covering timestamps {time_range}. "
        f"{context_line}"
        "Describe what you see in detail. Focus on:\n"
        "- What is happening (actions, transitions, costume changes, reveals)\n"
        "- Any CHANGES between frames (outfit swap, scene change, before/after)\n"
        "- Clothing/outfit details\n"
        "- Setting/location\n"
        "- Camera angles and movement\n"
        "Be concise but capture the SEQUENCE of events (3-4 sentences)."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the sequence of events in these frames. Note any transitions or changes."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ],
        "max_tokens": 300,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    response = requests.post(VLLM_API_URL, json=payload, timeout=ANALYSIS_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    content = data['choices'][0]['message']['content'].strip()
    
    import re
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return content

def _merge_observations(observations: list, model_name: str, extra_context: str = "") -> dict:
    """
    Sends all batch observations to the VLM to produce one final merged style profile JSON.
    Understands narrative structure: transitions, costume changes, story arcs.
    """
    combined = "\n".join([f"Batch {i+1} (chronological): {obs}" for i, obs in enumerate(observations)])
    
    system_prompt = (
        "You are an expert TikTok trend analyst. Below are chronological observations from analyzing "
        f"{len(observations)} sequential batches of frames from a TikTok trend video. "
        "The batches are in TIME ORDER — Batch 1 is the beginning, the last batch is the end.\n\n"
        "Your job is to understand the FULL NARRATIVE of this video and produce a JSON object with these keys:\n"
        "- 'video_type': What kind of TikTok is this? (e.g., 'transition/reveal', 'dance', 'tutorial', 'outfit showcase', 'comedy skit', 'before-and-after', 'cosplay transformation')\n"
        "- 'narrative': A 1-2 sentence description of what happens from start to finish\n"
        "- 'clothing': What to wear to recreate this (if it's a transition, describe BOTH the before and after outfits)\n"
        "- 'setting': Where it is filmed\n"
        "- 'camera_angle': The dominant camera angles used\n"
        "- 'key_transition': If there's a transition/reveal moment, describe it (e.g., 'hand covers camera, then reveals cosplay outfit'). Set to 'none' if no transition.\n"
        "- 'recreation_tips': 2-3 specific tips for someone trying to recreate this exact video\n\n"
        "Reply ONLY with the raw JSON object."
    )

    user_content = f"Here are the chronological observations:\n\n{combined}"
    if extra_context:
        user_content += f"\n\nAdditional analysis data:{extra_context}"
    user_content += "\n\nAnalyze the full narrative and provide the merged JSON."

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    response = requests.post(VLLM_API_URL, json=payload, timeout=ANALYSIS_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    content = data['choices'][0]['message']['content'].strip()
    
    import re
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    
    if content.startswith("```json"):
        content = content.split("```json")[1].split("```")[0].strip()
    elif content.startswith("```"):
        content = content.split("```")[1].split("```")[0].strip()
    
    json_match = re.search(r'\{.*\}', content, flags=re.DOTALL)
    if json_match:
        content = json_match.group(0)
    
    return json.loads(content)

def correlate_beats_and_cuts(beats: list, cuts: list, threshold: float = 0.15) -> list:
    """
    A4: Correlates beat timestamps with cut timestamps.
    Returns a list of sync events showing if cuts align with beats.
    """
    sync_data = []
    for cut_time in cuts:
        if not beats:
            sync_data.append({"cut_time": cut_time, "nearest_beat": None, "synced": False, "offset_ms": None})
            continue
        nearest_beat = min(beats, key=lambda b: abs(b - cut_time))
        offset = abs(nearest_beat - cut_time)
        sync_data.append({
            "cut_time": round(cut_time, 3),
            "nearest_beat": round(nearest_beat, 3),
            "synced": offset <= threshold,
            "offset_ms": round(offset * 1000, 1)
        })
    synced_count = sum(1 for s in sync_data if s["synced"])
    print(f"Beat-cut correlation: {synced_count}/{len(sync_data)} cuts are beat-synced (within {threshold*1000:.0f}ms)")
    return sync_data

def extract_style_profile(video_path: str, model_name: str = None, cuts: list = None,
                          beats: list = None):
    """
    Scene-cut-aligned, rolling-context style extraction:
    - Aligns frame sampling to scene boundaries (A1)
    - Feeds previous batch context into next batch (A2)
    - Skips blurry frames (A3, via sample_frames)
    - Includes beat-cut sync data in merge prompt (A4)
    """
    if model_name is None:
        model_name = ANALYSIS_MODEL
    
    print("Extracting style profile (scene-aligned batched analysis)...")

    # Sample frames — scene-aligned if cuts available
    frames = sample_frames(video_path, interval=0.3, cuts=cuts)
    
    if not frames:
        print("Failed to extract frames for style analysis.")
        return {"clothing": "casual", "setting": "well-lit room", "camera_angle": "medium shot"}
    
    # Split into batches of 9 (3x3 grids), respecting scene boundaries
    BATCH_SIZE = 9
    if cuts and len(cuts) >= 2:
        # Group frames by scene, then chunk each scene into batches of 9
        batches = []
        scene_idx = 0
        current_scene_frames = []
        for timestamp, frame in frames:
            # Move to next scene if we've passed the boundary
            while scene_idx < len(cuts) - 1 and timestamp >= cuts[scene_idx + 1]:
                # Flush current scene frames as batches
                if current_scene_frames:
                    for i in range(0, len(current_scene_frames), BATCH_SIZE):
                        batches.append(current_scene_frames[i:i + BATCH_SIZE])
                current_scene_frames = []
                scene_idx += 1
            current_scene_frames.append((timestamp, frame))
        # Flush remaining
        if current_scene_frames:
            for i in range(0, len(current_scene_frames), BATCH_SIZE):
                batches.append(current_scene_frames[i:i + BATCH_SIZE])
    else:
        batches = [frames[i:i + BATCH_SIZE] for i in range(0, len(frames), BATCH_SIZE)]

    total_batches = len(batches)
    print(f"Processing {total_batches} batches of up to {BATCH_SIZE} frames each...")
    
    observations = []
    previous_context = None  # A2: rolling context
    for idx, batch in enumerate(batches):
        time_start = f"{batch[0][0]:.1f}s"
        time_end = f"{batch[-1][0]:.1f}s"
        time_range = f"{time_start}-{time_end}"
        
        contact_sheet = create_contact_sheet(batch, thumb_width=320, cols=3)
        base64_image = encode_image_base64(contact_sheet)
        
        try:
            print(f"  Analyzing batch {idx+1}/{total_batches} ({time_range})...")
            obs = _analyze_batch(base64_image, idx+1, total_batches, len(batch),
                                time_range, model_name, previous_context=previous_context)
            print(f"  [Batch {idx+1}] {obs[:150]}")
            observations.append(obs)
            previous_context = obs  # Feed into next batch
        except Exception as e:
            print(f"  [Batch {idx+1}] Failed: {str(e)}")
    
    if not observations:
        print("All batches failed, falling back to mock.")
        return {
            "clothing": "streetwear or casual trendy outfit",
            "setting": "outdoor urban environment or well-lit bedroom",
            "camera_angle": "full body shot"
        }
    
    # Merge all observations into one final style profile
    try:
        print(f"Merging {len(observations)} batch observations into final style profile...")

        # A4: Add beat-cut correlation info to merge context
        beat_sync_info = ""
        if beats and cuts:
            sync_data = correlate_beats_and_cuts(beats, cuts)
            synced_count = sum(1 for s in sync_data if s["synced"])
            beat_sync_info = f"\nBeat-cut sync: {synced_count}/{len(sync_data)} cuts are rhythmically aligned with beats."

        style_data = _merge_observations(observations, model_name, extra_context=beat_sync_info)
        print(f"[DEBUG] Merged style: {style_data}")
        return {
            "video_type": style_data.get("video_type", "unknown"),
            "narrative": style_data.get("narrative", ""),
            "clothing": style_data.get("clothing", "casual outfit"),
            "setting": style_data.get("setting", "well-lit environment"),
            "camera_angle": style_data.get("camera_angle", "medium shot"),
            "key_transition": style_data.get("key_transition", "none"),
            "recreation_tips": style_data.get("recreation_tips", "")
        }
    except Exception as e:
        print(f"Merge failed (falling back to mock): {str(e)}")
        return {
            "video_type": "unknown",
            "narrative": "",
            "clothing": "streetwear or casual trendy outfit",
            "setting": "outdoor urban environment or well-lit bedroom",
            "camera_angle": "full body shot",
            "key_transition": "none",
            "recreation_tips": ""
        }

def interpolate_pose_gaps(pose_timeline: list, sample_interval: float = 0.1) -> list:
    """
    A5: Fills gaps in pose timeline with linear interpolation.
    If MediaPipe lost tracking for some frames, this fills in the blanks.
    """
    if len(pose_timeline) < 2:
        return pose_timeline

    interpolated = 0
    filled = list(pose_timeline)

    for i in range(len(filled) - 1):
        t1 = filled[i]["time"]
        t2 = filled[i + 1]["time"]
        gap = t2 - t1

        if gap > sample_interval * 2.5:
            # Insert interpolated poses
            n_missing = int(gap / sample_interval) - 1
            for j in range(1, n_missing + 1):
                alpha = j / (n_missing + 1)
                interp_time = round(t1 + alpha * gap, 2)

                # Linear interpolation of normalized landmarks
                norm1 = filled[i]["normalized"]
                norm2 = filled[i + 1]["normalized"]
                interp_norm = []
                interp_lm = []
                for k in range(min(len(norm1), len(norm2))):
                    interp_norm.append([
                        norm1[k][0] + alpha * (norm2[k][0] - norm1[k][0]),
                        norm1[k][1] + alpha * (norm2[k][1] - norm1[k][1]),
                        norm1[k][2] + alpha * (norm2[k][2] - norm1[k][2]),
                        min(norm1[k][3], norm2[k][3]) * 0.5  # Lower visibility for interpolated
                    ])
                    lm1 = filled[i]["landmarks"][k]
                    lm2 = filled[i + 1]["landmarks"][k]
                    interp_lm.append([
                        lm1[0] + alpha * (lm2[0] - lm1[0]),
                        lm1[1] + alpha * (lm2[1] - lm1[1]),
                        lm1[2] + alpha * (lm2[2] - lm1[2]),
                        min(lm1[3], lm2[3]) * 0.5
                    ])

                filled.append({
                    "time": interp_time,
                    "landmarks": interp_lm,
                    "normalized": interp_norm,
                    "interpolated": True
                })
                interpolated += 1

    filled.sort(key=lambda p: p["time"])
    if interpolated > 0:
        print(f"Pose interpolation: filled {interpolated} gap frames")
    return filled

def analyze_trend(url: str, output_dir: str = "temp"):
    """
    End-to-end analysis pipeline:
    1. Download video
    2. Extract audio → beats
    3. Find scene cuts
    4. Correlate beats ↔ cuts (A4)
    5. Analyze camera motion (optical flow)
    6. Extract reference poses + interpolate gaps (A5)
    7. Extract style profile (scene-aligned, rolling context, blur-aware) (A1-A3)
    8. Save Skill archive
    """
    try:
        video_path = download_video(url, output_dir)
        audio_path = os.path.join(output_dir, "extracted_audio.mp3")
        extract_audio(video_path, audio_path)

        bpm, beats = detect_audio_beats(audio_path)
        cuts = detect_video_cuts(video_path)
        
        # A4: Beat-cut correlation
        beat_cut_sync = correlate_beats_and_cuts(beats, cuts)

        # Camera motion analysis (optical flow)
        camera_motion = analyze_camera_motion(video_path)
        
        # Reference pose extraction + A5: interpolation
        reference_poses = extract_reference_poses(video_path)
        if reference_poses:
            reference_poses = interpolate_pose_gaps(reference_poses)

        # C2: Depth estimation (optional — requires GPU + weights)
        depth_profile = []
        try:
            from depth_estimator import DepthEstimator
            depth_est = DepthEstimator()
            if depth_est.available:
                depth_profile = depth_est.extract_reference_depth(video_path)
        except Exception as e:
            print(f"Depth estimation skipped: {e}")
        
        # VLM-based style profile — now scene-aligned with rolling context
        style = extract_style_profile(video_path, cuts=cuts, beats=beats)

        context = {
            "bpm": bpm,
            "cuts": cuts,
            "beats": beats,
            "beat_cut_sync": beat_cut_sync,
            "audio_path": audio_path,
            "reference_video_path": video_path,
            "camera_motion": camera_motion,
            "depth_profile": depth_profile,
        }

        trend_name = "trend_" + os.path.basename(video_path).split('.')[0]
        skill_dir = save_skill(trend_name, style, context, reference_poses)

        print(f"Trend analysis complete! Skill saved to {skill_dir}")
        return skill_dir, style, context

    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        raise e

if __name__ == "__main__":
    # Test block
    print("Run app.py to start the full Gradio interface.")

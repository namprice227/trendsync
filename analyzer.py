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

VLLM_API_URL = "http://localhost:8000/v1/chat/completions"

import numpy as np

def encode_image_base64(frame):
    """Encodes a cv2 image frame to base64 string."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')

def sample_frames(video_path: str, interval: float = 0.3):
    """
    Samples frames from the video at the given interval (in seconds).
    Returns a list of (timestamp, frame) tuples.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    frames = []
    current_time = 0.0
    while current_time < duration:
        frame_idx = int(current_time * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret:
            frames.append((current_time, frame))
        current_time += interval
    
    cap.release()
    print(f"Sampled {len(frames)} frames at {interval}s intervals ({duration:.1f}s video)")
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
                   num_frames: int, time_range: str, model_name: str) -> str:
    """
    Sends a single 3x3 contact sheet batch to the VLM.
    Returns the raw text observation from the model.
    """
    # Tell the model where in the video timeline this batch falls
    position = "beginning" if batch_num <= total_batches * 0.33 else ("middle" if batch_num <= total_batches * 0.66 else "end")
    
    system_prompt = (
        "You are an expert TikTok trend analyst studying viral video patterns. "
        f"This is batch {batch_num}/{total_batches} (the {position}) of a TikTok video. "
        f"The image is a 3x3 grid of {num_frames} frames covering timestamps {time_range}. "
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

    response = requests.post(VLLM_API_URL, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    content = data['choices'][0]['message']['content'].strip()
    
    import re
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return content

def _merge_observations(observations: list, model_name: str) -> dict:
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

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here are the chronological observations:\n\n{combined}\n\nAnalyze the full narrative and provide the merged JSON."}
        ],
        "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    response = requests.post(VLLM_API_URL, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    content = data['choices'][0]['message']['content'].strip()
    
    import re
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    
    if content.startswith("```json"):
        content = content.split("```json")[1].split("```")[0].strip()
    elif content.startswith("```"):
        content = content.split("```")[1].split("```")[0].strip()
    
    # Find JSON — may be nested, so use a greedy match
    json_match = re.search(r'\{.*\}', content, flags=re.DOTALL)
    if json_match:
        content = json_match.group(0)
    
    return json.loads(content)

def extract_style_profile(video_path: str, model_name: str = "Qwen/Qwen3.6-35B-A3B"):
    """
    Samples frames every 0.3s, groups them into 3x3 batches (9 frames each),
    analyzes each batch with the VLM, then merges all observations into a 
    single style profile with one final VLM call.
    """
    print("Extracting style profile (batched 3x3 analysis)...")
    
    # Sample frames every 0.3 seconds
    frames = sample_frames(video_path, interval=0.3)
    
    if not frames:
        print("Failed to extract frames for style analysis.")
        return {"clothing": "casual", "setting": "well-lit room", "camera_angle": "medium shot"}
    
    # Split into batches of 9 (3x3 grids)
    BATCH_SIZE = 9
    batches = [frames[i:i + BATCH_SIZE] for i in range(0, len(frames), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"Processing {total_batches} batches of up to {BATCH_SIZE} frames each...")
    
    observations = []
    for idx, batch in enumerate(batches):
        time_start = f"{batch[0][0]:.1f}s"
        time_end = f"{batch[-1][0]:.1f}s"
        time_range = f"{time_start}-{time_end}"
        
        contact_sheet = create_contact_sheet(batch, thumb_width=320, cols=3)
        base64_image = encode_image_base64(contact_sheet)
        
        try:
            print(f"  Analyzing batch {idx+1}/{total_batches} ({time_range})...")
            obs = _analyze_batch(base64_image, idx+1, total_batches, len(batch), time_range, model_name)
            print(f"  [Batch {idx+1}] {obs[:150]}")
            observations.append(obs)
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
        style_data = _merge_observations(observations, model_name)
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

def analyze_trend(url: str, output_dir: str = "temp"):
    """
    End-to-end analysis:
    1. Download video
    2. Extract audio
    3. Find beats
    4. Find cuts
    5. Save trend_profile.json
    """
    try:
        video_path = download_video(url, output_dir)
        audio_path = os.path.join(output_dir, "extracted_audio.mp3")
        extract_audio(video_path, audio_path)

        bpm, beats = detect_audio_beats(audio_path)
        cuts = detect_video_cuts(video_path)
        style = extract_style_profile(video_path)

        context = {
            "bpm": bpm,
            "cuts": cuts,
            "beats": beats,
            "audio_path": audio_path,
            "reference_video_path": video_path,
        }

        # Use the video ID as the trend name (extracted from URL or fallback)
        trend_name = "trend_" + os.path.basename(video_path).split('.')[0]
        skill_dir = save_skill(trend_name, style, context)

        print(f"Trend analysis complete! Skill saved to {skill_dir}")
        return skill_dir, style, context

    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        raise e

if __name__ == "__main__":
    # Test block
    print("Run app.py to start the full Gradio interface.")

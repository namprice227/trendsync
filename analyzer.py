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
        # yt-dlp might change the extension, let's get the actual file if possible, or just default.
        # Sometimes 'prepare_filename' gets the final name right

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

def encode_image_base64(frame):
    """Encodes a cv2 image frame to base64 string."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')

def extract_style_profile(video_path: str, model_name: str = "Qwen/Qwen3.6-35B-A3B"):
    """
    Extracts a frame from the video and queries the VLM for style profile.
    Falls back to a mock if the server isn't reachable.
    """
    print("Extracting style profile...")
    cap = cv2.VideoCapture(video_path)
    # Get a frame from the middle of the video
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Failed to extract frame for style analysis.")
        return {"clothing": "casual", "setting": "well-lit room", "camera_angle": "medium shot"}

    base64_image = encode_image_base64(frame)

    system_prompt = (
        "You are an expert cinematographer analyzing a TikTok trend. "
        "Analyze the provided frame and output a JSON object with exactly these three keys: "
        "'clothing' (what the person is wearing), 'setting' (where it is filmed), and 'camera_angle' (e.g., full body, close up). "
        "Reply ONLY with the raw JSON object."
    )

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this frame and provide the JSON."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 150
    }

    try:
        response = requests.post(VLLM_API_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content'].strip()
        
        # Try to parse the JSON returned by the VLM
        # Sometimes models wrap JSON in markdown blocks
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
            
        style_data = json.loads(content)
        
        # Ensure keys exist
        return {
            "clothing": style_data.get("clothing", "casual outfit"),
            "setting": style_data.get("setting", "well-lit environment"),
            "camera_angle": style_data.get("camera_angle", "medium shot")
        }
    except Exception as e:
        print(f"VLM API failed (falling back to mock): {str(e)}")
        # Mock VLM style extraction if vLLM server isn't running
        return {
            "clothing": "streetwear or casual trendy outfit",
            "setting": "outdoor urban environment or well-lit bedroom",
            "camera_angle": "full body shot"
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

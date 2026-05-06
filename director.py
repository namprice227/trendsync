import cv2
import base64
import requests
import time
import json
import os

# OpenAI API endpoint for vLLM local server
VLLM_API_URL = "http://localhost:8000/v1/chat/completions"

def encode_image_base64(frame):
    """Encodes a cv2 image frame to base64 string."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')

def get_vlm_feedback(base64_image: str, model_name: str = "Qwen/Qwen3.5-VL-27B-Instruct") -> str:
    """
    Sends the base64 encoded image to the local vLLM server and returns the feedback.
    """
    system_prompt = (
        "You are a film director. The user needs to frame a medium-close-up shot. "
        "Look at the attached camera frame. Is the user centered? Is the lighting good? "
        "Reply ONLY with brief instructions like 'Move left', 'Too dark', or 'Perfect'."
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
                    {"type": "text", "text": "Evaluate this frame."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 10
    }

    try:
        response = requests.post(VLLM_API_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        # If API fails (e.g., vLLM not running), return a placeholder message.
        return f"API Error (Ensure vLLM is running at localhost:8000): {str(e)}"

def capture_shot(duration_seconds: float, output_path: str, camera_index: int = 0):
    """
    Captures a video for a specific duration after the VLM says 'Perfect'.
    Since this might run via Gradio, we separate the capture logic.
    """
    cap = cv2.VideoCapture(camera_index)

    # Get default video dimensions
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))

    start_time = time.time()
    while (time.time() - start_time) < duration_seconds:
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)

    cap.release()
    out.release()
    return output_path

if __name__ == "__main__":
    print("Director module loaded. Use app.py for the full UI.")

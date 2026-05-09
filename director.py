import cv2
import base64
import requests
import json
import time
import numpy as np
from config import DIRECTOR_VLLM_API_URL, DIRECTOR_MODEL, DIRECTOR_TIMEOUT, DIRECTOR_VLM_INTERVAL, vlm_request_with_retry
from pose_utils import create_pose_estimator, compute_pose_dtw_score

VLLM_API_URL = DIRECTOR_VLLM_API_URL

def encode_image_base64(frame):
    """Encodes a cv2 image frame to base64 string."""
    _, buffer = cv2.imencode('.jpg', frame)
    return base64.b64encode(buffer).decode('utf-8')

# ============================================================
# POSE TRACKER — Real-time pose comparison using MediaPipe + DTW
# ============================================================

class PoseTracker:
    """
    Wraps MediaPipe Pose for real-time skeleton extraction and 
    DTW-based comparison against reference poses.
    """
    
    # Key joint names for human-readable feedback
    JOINT_NAMES = {
        0: "nose", 11: "left shoulder", 12: "right shoulder",
        13: "left elbow", 14: "right elbow", 15: "left wrist", 16: "right wrist",
        23: "left hip", 24: "right hip", 25: "left knee", 26: "right knee",
        27: "left ankle", 28: "right ankle"
    }
    
    def __init__(self):
        self._pose_estimator = None
        self._available = False
        self._pose_history = []  # Buffer of recent normalized poses
        self._max_history = 30   # ~3 seconds at 10fps

        self._pose_estimator = create_pose_estimator(
            static_image_mode=False,
            # Complexity 1 ships with MediaPipe; 0/2 trigger first-run downloads.
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            log_prefix="PoseTracker",
        )
        if self._pose_estimator is not None:
            self._available = True
    
    @property
    def available(self):
        return self._available
    
    def extract_pose(self, frame_rgb):
        """
        Extracts normalized pose landmarks from an RGB frame.
        Returns (landmarks_list, normalized_list) or (None, None) if no person detected.
        """
        if not self._available:
            return None, None
        
        landmarks, normalized = self._pose_estimator.extract(frame_rgb)
        if not normalized:
            return None, None
        
        # Add to history buffer
        self._pose_history.append(normalized)
        if len(self._pose_history) > self._max_history:
            self._pose_history.pop(0)
        
        return landmarks, normalized
    
    def compare_to_reference(self, current_normalized, reference_poses, current_time):
        """
        Compares the current pose to the reference pose at the matching timestamp.
        Returns a feedback string with specific joint deviations.
        """
        if not reference_poses or current_normalized is None:
            return None
        
        # Find the closest reference pose by time
        closest_ref = min(reference_poses, key=lambda p: abs(p["time"] - current_time))
        ref_normalized = closest_ref["normalized"]
        
        # Compare key joints and find the biggest deviation
        deviations = []
        for joint_id, joint_name in self.JOINT_NAMES.items():
            if joint_id >= len(current_normalized) or joint_id >= len(ref_normalized):
                continue
            
            curr = current_normalized[joint_id]
            ref = ref_normalized[joint_id]
            
            # Only compare if both have good visibility
            if curr[3] < 0.5 or ref[3] < 0.5:
                continue
            
            dx = curr[0] - ref[0]
            dy = curr[1] - ref[1]
            deviation = np.sqrt(dx**2 + dy**2)
            
            if deviation > 0.05:  # Threshold: 5% of body scale
                # Determine direction
                direction = ""
                if abs(dx) > abs(dy):
                    direction = "right" if dx > 0 else "left"
                else:
                    direction = "down" if dy > 0 else "up"
                
                pct = int(deviation * 100)
                deviations.append((pct, f"{joint_name} {pct}% too far {direction}"))
        
        if not deviations:
            return "🎯 Pose matches reference!"
        
        # Sort by largest deviation first, return top 2
        deviations.sort(reverse=True)
        feedback_parts = [d[1] for d in deviations[:2]]
        return "📐 " + " | ".join(feedback_parts)
    
    def compute_dtw_score(self, reference_poses):
        """
        Computes DTW distance between the recent pose history and the reference sequence.
        Returns (score, temporal_offset_hint) or (None, None) if not enough data.
        """
        if len(self._pose_history) < 5 or not reference_poses:
            return None, None
        
        score = compute_pose_dtw_score(self._pose_history, reference_poses)
        if score is None:
            return None, None
        return score, None

    def compute_sequence_dtw_score(self, user_poses, reference_poses):
        """Computes a 0-100 DTW similarity score for uploaded clip poses."""
        return compute_pose_dtw_score(user_poses, reference_poses)
    
    def close(self):
        if self._pose_estimator:
            self._pose_estimator.close()

# ============================================================
# CAMERA MOTION CHECK — Compare user's camera to reference
# ============================================================

def check_camera_motion(prev_gray, curr_gray, expected_motion: str):
    """
    Checks if the user's current camera motion matches the expected motion.
    Returns (actual_motion, feedback_string).
    """
    if prev_gray is None or curr_gray is None:
        return "unknown", None
    
    # Resize for speed
    h, w = 240, 320
    prev_small = cv2.resize(prev_gray, (w, h))
    curr_small = cv2.resize(curr_gray, (w, h))
    
    flow = cv2.calcOpticalFlowFarneback(prev_small, curr_small, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    fx, fy = flow[..., 0], flow[..., 1]
    
    mean_dx = float(np.mean(fx))
    mean_dy = float(np.mean(fy))
    magnitude = float(np.sqrt(mean_dx**2 + mean_dy**2))
    
    PAN_THRESHOLD = 1.5
    
    if magnitude > PAN_THRESHOLD:
        if abs(mean_dx) > abs(mean_dy):
            actual = "pan_right" if mean_dx > 0 else "pan_left"
        else:
            actual = "pan_down" if mean_dy > 0 else "pan_up"
    else:
        actual = "static"
    
    # Compare to expected
    if expected_motion == "static" and actual == "static":
        return actual, None  # No feedback needed
    elif expected_motion != "static" and actual == "static":
        motion_readable = expected_motion.replace("_", " ").title()
        return actual, f"🎥 Camera: {motion_readable} now!"
    elif expected_motion == actual:
        return actual, "🎥 Camera motion matches! ✓"
    elif expected_motion == "static" and actual != "static":
        return actual, "🎥 Keep camera still!"
    
    return actual, None

# ============================================================
# FAST FEEDBACK LOOP — CV-based (runs on every frame, no GPU)
# ============================================================

def get_fast_feedback(frame_rgb, pose_tracker, reference_poses, camera_motion_timeline,
                      current_time, prev_gray=None):
    """
    Fast CV-based feedback that runs on every frame (CPU only, no VLM).
    Returns (feedback_string, new_prev_gray).
    """
    feedback_parts = []
    
    # 1. Pose comparison
    if pose_tracker and pose_tracker.available:
        landmarks, normalized = pose_tracker.extract_pose(frame_rgb)
        if normalized and reference_poses:
            pose_fb = pose_tracker.compare_to_reference(normalized, reference_poses, current_time)
            if pose_fb:
                feedback_parts.append(pose_fb)
    
    # 2. Camera motion check
    curr_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    if camera_motion_timeline and prev_gray is not None:
        # Find expected motion at current time
        closest_motion = min(camera_motion_timeline, key=lambda m: abs(m["time"] - current_time))
        expected = closest_motion["motion"]
        _, cam_fb = check_camera_motion(prev_gray, curr_gray, expected)
        if cam_fb:
            feedback_parts.append(cam_fb)
    
    feedback = " | ".join(feedback_parts) if feedback_parts else "Analyzing..."
    return feedback, curr_gray

# ============================================================
# SLOW FEEDBACK LOOP — VLM-based (runs every 2-3 seconds, GPU)
# ============================================================

def get_vlm_feedback(base64_image: str, system_prompt: str = None, model_name: str = None,
                     cv_context: str = None) -> str:
    """
    Sends the base64 encoded image to the local vLLM server and returns the feedback.
    B1: If cv_context is provided, injects CV pipeline observations into the prompt.
    Falls back to a mock response if the server is not reachable.
    """
    if model_name is None:
        model_name = DIRECTOR_MODEL
    
    if not system_prompt:
        system_prompt = (
            "You are a film director. "
            "Look at the attached camera frame. Is the user matching the style? Is the user centered? Is the lighting good? "
            "Reply ONLY with brief instructions like 'Move left', 'Too dark', 'Change outfit', or 'Perfect'."
        )
    
    # B1: Inject CV observations into the prompt
    if cv_context:
        system_prompt += (
            f"\n\nThe computer vision pipeline detected the following about the user's current frame:\n"
            f"{cv_context}\n"
            "Use this information to give more precise, actionable feedback."
        )

    user_text = "Evaluate this frame."

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
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 80,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    try:
        data = vlm_request_with_retry(VLLM_API_URL, payload, timeout=DIRECTOR_TIMEOUT)
        content = data['choices'][0]['message']['content'].strip()
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        import random
        time.sleep(1)
        if random.random() > 0.6:
            return "Perfect"
        else:
            return "Match the requested outfit or improve lighting."

def capture_shot(duration_seconds: float, output_path: str, camera_index: int = 0):
    """
    Captures a video for a specific duration after the VLM says 'Perfect'.
    Since this might run via Gradio, we separate the capture logic.
    """
    cap = cv2.VideoCapture(camera_index)

    # Get default video dimensions
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fps = 30.0

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
    print(f"Shot captured to {output_path} (duration: {duration_seconds:.1f}s)")

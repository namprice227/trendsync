"""
Depth Estimation Module — Uses Depth Anything V2 for scene depth analysis.

This module runs on the MI300X GPU alongside vLLM. It helps the Director
understand if the user is too close/far from the camera compared to the
reference video's depth profile.

Requires: pip install transformers torch (with ROCm)
"""

import cv2
import numpy as np
import os

class DepthEstimator:
    """
    Wraps Depth Anything V2 for monocular depth estimation.
    Used to compare reference video depth profile against user's live camera.
    """
    
    def __init__(self, model_size: str = "Small"):
        """
        Initialize the depth estimator.
        model_size: "Small" (24.8M params), "Base" (97.5M), "Large" (335.3M)
        """
        self._available = False
        self._model = None
        self._transform = None
        
        try:
            import torch
            if not torch.cuda.is_available():
                print("[DepthEstimator] No GPU available — depth estimation disabled")
                return
            
            # Try loading from local clone first
            local_path = os.path.join(os.path.dirname(__file__), "Depth-Anything-V2")
            if os.path.exists(local_path):
                import sys
                sys.path.insert(0, local_path)
                from depth_anything_v2.dpt import DepthAnythingV2
                
                model_configs = {
                    'Small': {'encoder': 'vits', 'features': 64, 'out_channels': [48, 96, 192, 384]},
                    'Base': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
                    'Large': {'encoder': 'vitl', 'features': 256, 'out_channels': [256, 512, 1024, 1024]},
                }
                
                config = model_configs.get(model_size, model_configs['Small'])
                self._model = DepthAnythingV2(**config)
                
                # Check for pretrained weights
                weights_path = os.path.join(local_path, f"checkpoints/depth_anything_v2_vit{config['encoder'][3]}.pth")
                if os.path.exists(weights_path):
                    self._model.load_state_dict(torch.load(weights_path, map_location='cuda', weights_only=True))
                    self._model = self._model.cuda().eval()
                    self._available = True
                    print(f"[DepthEstimator] Loaded Depth Anything V2 {model_size} from local weights")
                else:
                    print(f"[DepthEstimator] Weights not found at {weights_path}")
                    print(f"  Download from: https://huggingface.co/depth-anything/Depth-Anything-V2-{model_size}/resolve/main/depth_anything_v2_vit{config['encoder'][3]}.pth")
            else:
                print(f"[DepthEstimator] Depth-Anything-V2 repo not found at {local_path}")
                
        except ImportError as e:
            print(f"[DepthEstimator] Dependencies not available: {e}")
        except Exception as e:
            print(f"[DepthEstimator] Failed to initialize: {e}")
    
    @property
    def available(self):
        return self._available
    
    def estimate_depth(self, frame_bgr):
        """
        Estimates depth from a BGR frame.
        Returns a normalized depth map (0.0 = near, 1.0 = far).
        """
        if not self._available:
            return None
        
        import torch
        
        with torch.no_grad():
            depth = self._model.infer_image(frame_bgr)
        
        # Normalize to 0-1
        depth_norm = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)
        return depth_norm
    
    def compare_depth_profiles(self, ref_depth_map, user_depth_map):
        """
        Compares two depth maps and gives feedback.
        Returns a feedback string or None if no significant difference.
        """
        if ref_depth_map is None or user_depth_map is None:
            return None
        
        # Resize to match
        h, w = 240, 320
        ref_resized = cv2.resize(ref_depth_map, (w, h))
        user_resized = cv2.resize(user_depth_map, (w, h))
        
        # Compare center region (where subject usually is)
        ch, cw = h // 4, w // 4
        ref_center = ref_resized[ch:3*ch, cw:3*cw]
        user_center = user_resized[ch:3*ch, cw:3*cw]
        
        ref_mean = float(np.mean(ref_center))
        user_mean = float(np.mean(user_center))
        
        diff = user_mean - ref_mean
        
        if abs(diff) > 0.15:
            if diff > 0:
                return "📏 Move closer to the camera — you're too far back"
            else:
                return "📏 Step back from the camera — you're too close"
        
        return None
    
    def extract_reference_depth(self, video_path: str, sample_interval: float = 1.0):
        """
        Extracts average depth profile from the reference video.
        Returns a list of depth statistics per sampled frame.
        """
        if not self._available:
            return []
        
        print("Extracting reference depth profile...")
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        depth_profiles = []
        current_time = 0.0
        
        while current_time < duration:
            frame_idx = int(current_time * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            
            depth_map = self.estimate_depth(frame)
            if depth_map is not None:
                depth_profiles.append({
                    "time": round(current_time, 2),
                    "mean_depth": float(np.mean(depth_map)),
                    "std_depth": float(np.std(depth_map))
                })
            
            current_time += sample_interval
        
        cap.release()
        print(f"Depth profile extracted: {len(depth_profiles)} samples")
        return depth_profiles


# Quick test
if __name__ == "__main__":
    estimator = DepthEstimator()
    print(f"Depth Anything V2 available: {estimator.available}")

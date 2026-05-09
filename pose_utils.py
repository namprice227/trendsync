import os

import numpy as np


_WARNED = set()


def _warn_once(key: str, message: str):
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(message)


def _serialize_landmarks(raw_landmarks):
    landmarks = []
    for lm in raw_landmarks:
        visibility = getattr(lm, "visibility", None)
        if visibility is None:
            visibility = getattr(lm, "presence", 1.0)
        landmarks.append([
            float(lm.x),
            float(lm.y),
            float(lm.z),
            float(visibility if visibility is not None else 1.0),
        ])
    return landmarks


def normalize_landmarks(landmarks):
    if not landmarks or len(landmarks) <= 24:
        return []

    hip_x = (landmarks[23][0] + landmarks[24][0]) / 2
    hip_y = (landmarks[23][1] + landmarks[24][1]) / 2
    hip_z = (landmarks[23][2] + landmarks[24][2]) / 2

    return [
        [lm[0] - hip_x, lm[1] - hip_y, lm[2] - hip_z, lm[3]]
        for lm in landmarks
    ]


class _LegacyPoseEstimator:
    def __init__(self, pose):
        self._pose = pose

    def extract(self, frame_rgb):
        results = self._pose.process(frame_rgb)
        if not results.pose_landmarks:
            return None, None

        landmarks = _serialize_landmarks(results.pose_landmarks.landmark)
        normalized = normalize_landmarks(landmarks)
        return landmarks, normalized if normalized else None

    def close(self):
        self._pose.close()


class _TasksPoseEstimator:
    def __init__(self, mp, landmarker):
        self._mp = mp
        self._landmarker = landmarker

    def extract(self, frame_rgb):
        frame_rgb = np.ascontiguousarray(frame_rgb)
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=frame_rgb,
        )
        results = self._landmarker.detect(image)
        if not results.pose_landmarks:
            return None, None

        landmarks = _serialize_landmarks(results.pose_landmarks[0])
        normalized = normalize_landmarks(landmarks)
        return landmarks, normalized if normalized else None

    def close(self):
        self._landmarker.close()


def create_pose_estimator(
    *,
    static_image_mode: bool,
    model_complexity: int = 1,
    min_detection_confidence: float = 0.5,
    min_tracking_confidence: float = 0.5,
    log_prefix: str = "MediaPipe",
):
    """
    Creates a pose estimator for either the legacy MediaPipe Solutions API or,
    when explicitly configured, the newer MediaPipe Tasks API.

    Python 3.13 MediaPipe wheels currently expose Tasks without
    mediapipe.solutions, so callers must treat a missing estimator as an
    optional feature and continue the rest of the workflow.
    """
    try:
        import mediapipe as mp
    except ImportError:
        _warn_once(
            f"{log_prefix}:missing",
            f"[{log_prefix}] MediaPipe is not installed; pose tracking disabled.",
        )
        return None

    solutions = getattr(mp, "solutions", None)
    pose_module = getattr(solutions, "pose", None) if solutions is not None else None
    if pose_module is not None:
        pose = pose_module.Pose(
            static_image_mode=static_image_mode,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        print(f"[{log_prefix}] MediaPipe legacy pose initialized")
        return _LegacyPoseEstimator(pose)

    model_path = os.environ.get("TRENDFLOW_POSE_LANDMARKER_MODEL")
    if not model_path:
        _warn_once(
            f"{log_prefix}:tasks_no_model",
            (
                f"[{log_prefix}] MediaPipe {getattr(mp, '__version__', 'unknown')} "
                "does not expose mediapipe.solutions in this Python environment. "
                "Pose tracking will be skipped. To enable it here, set "
                "TRENDFLOW_POSE_LANDMARKER_MODEL to a MediaPipe pose_landmarker.task "
                "file, or run the app with Python 3.9-3.12 and a legacy-solutions "
                "MediaPipe build."
            ),
        )
        return None

    if not os.path.exists(model_path):
        _warn_once(
            f"{log_prefix}:tasks_bad_model",
            f"[{log_prefix}] Pose task model not found at {model_path}; pose tracking disabled.",
        )
        return None

    try:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        options = vision.PoseLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.IMAGE,
            min_pose_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        landmarker = vision.PoseLandmarker.create_from_options(options)
        print(f"[{log_prefix}] MediaPipe Tasks pose initialized from {model_path}")
        return _TasksPoseEstimator(mp, landmarker)
    except Exception as exc:
        _warn_once(
            f"{log_prefix}:tasks_failed",
            f"[{log_prefix}] Failed to initialize MediaPipe Tasks pose model: {exc}",
        )
        return None


def _pose_from_entry(entry):
    if isinstance(entry, dict):
        return entry.get("normalized") or entry.get("landmarks")
    return entry


def _flatten_pose_sequence(poses):
    key_joints = [11, 12, 13, 14, 15, 16, 23, 24]
    flattened = []

    for entry in poses or []:
        pose = _pose_from_entry(entry)
        if not pose:
            continue

        coords = []
        for joint_id in key_joints:
            if joint_id < len(pose) and len(pose[joint_id]) >= 2:
                coords.extend([float(pose[joint_id][0]), float(pose[joint_id][1])])
            else:
                coords.extend([0.0, 0.0])
        flattened.append(coords)

    if not flattened:
        return None
    return np.array(flattened, dtype=np.float64)


def compute_pose_dtw_score(user_poses, reference_poses):
    """
    Returns a 0-100 similarity score for two normalized pose sequences.
    """
    user_seq = _flatten_pose_sequence(user_poses)
    ref_seq = _flatten_pose_sequence(reference_poses)
    if user_seq is None or ref_seq is None or len(user_seq) < 2 or len(ref_seq) < 2:
        return None

    try:
        from dtaidistance import dtw_ndim

        distance = dtw_ndim.distance_fast(user_seq, ref_seq, use_pruning=True)
    except Exception:
        n = min(len(user_seq), len(ref_seq))
        if n == 0:
            return None
        distance = float(np.linalg.norm(user_seq[:n] - ref_seq[:n]))

    norm_distance = distance / max(len(user_seq), len(ref_seq), 1)
    score = 100.0 - (norm_distance * 50.0)
    return round(max(0.0, min(100.0, score)), 1)

"""Gaze Estimator — converts facial landmarks to pitch/yaw angles.

PHASE 1 (STUB): Uses MediaPipe head pose via solvePnP as a rough
approximation. Returns head orientation angles.

PHASE 2 (REAL): Will load the frozen MLP model trained on MPIIGaze.
The interface stays the same: estimate_gaze(landmarks) → (pitch, yaw).

The clean interface ensures the detection pipeline doesn't change
when we swap stub → real model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass
class GazeResult:
    """Result from gaze estimation."""
    pitch: float = 0.0  # degrees, vertical
    yaw: float = 0.0    # degrees, horizontal
    valid: bool = False


# MediaPipe Face Mesh landmark indices for iris and eye corners
# These are the inputs to the future MLP model
IRIS_LANDMARKS = {
    "left_iris": [468, 469, 470, 471],    # Left iris ring
    "right_iris": [473, 474, 475, 476],   # Right iris ring
    "left_eye_inner": 133,
    "left_eye_outer": 33,
    "right_eye_inner": 362,
    "right_eye_outer": 263,
}

# 3D model points for head pose estimation (canonical face model)
_MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),          # Nose tip (1)
    (0.0, -330.0, -65.0),     # Chin (152)
    (-225.0, 170.0, -135.0),  # Left eye corner (33)
    (225.0, 170.0, -135.0),   # Right eye corner (263)
    (-150.0, -150.0, -125.0), # Left mouth corner (61)
    (150.0, -150.0, -125.0),  # Right mouth corner (291)
], dtype=np.float64)

# Corresponding MediaPipe landmark indices
_FACE_INDICES = [1, 152, 33, 263, 61, 291]


class GazeEstimator:
    """Estimates gaze direction from facial landmarks.

    Phase 1: Uses OpenCV solvePnP for head pose estimation.
    Phase 2: Will use a frozen MLP model trained on MPIIGaze.
    """

    def __init__(self, frame_width: int = 640, frame_height: int = 480):
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Camera matrix (approximate for typical webcam)
        focal_length = frame_width
        center = (frame_width / 2, frame_height / 2)
        self._camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)

        self._dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        # TODO Phase 2: Load frozen MLP model here
        # self._model = load_model("models/gaze_mlp.pkl")
        self._use_mlp = False

    def estimate(self, landmarks: np.ndarray) -> GazeResult:
        """Estimate gaze direction from MediaPipe landmarks.

        Args:
            landmarks: (478, 3) array of normalized face landmarks from MediaPipe.

        Returns:
            GazeResult with pitch and yaw in degrees.
        """
        if landmarks is None or len(landmarks) < 468:
            return GazeResult(valid=False)

        if self._use_mlp:
            return self._estimate_mlp(landmarks)
        else:
            return self._estimate_head_pose(landmarks)

    def _estimate_head_pose(self, landmarks: np.ndarray) -> GazeResult:
        """Phase 1 stub: head pose via solvePnP.

        Uses 6 key landmarks to estimate 3D head orientation.
        This is a rough approximation — the real MLP model will be more accurate.
        """
        # Extract 2D image points from normalized landmarks
        image_points = np.array([
            [
                landmarks[idx, 0] * self.frame_width,
                landmarks[idx, 1] * self.frame_height,
            ]
            for idx in _FACE_INDICES
        ], dtype=np.float64)

        # Solve PnP
        success, rotation_vec, translation_vec = cv2.solvePnP(
            _MODEL_POINTS,
            image_points,
            self._camera_matrix,
            self._dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success:
            return GazeResult(valid=False)

        # Convert rotation vector to Euler angles
        rotation_mat, _ = cv2.Rodrigues(rotation_vec)
        pose_mat = cv2.hconcat([rotation_mat, translation_vec])
        _, _, _, _, _, _, euler = cv2.decomposeProjectionMatrix(
            np.vstack([pose_mat, [0, 0, 0, 1]])[:3]
        )

        pitch = float(euler[0, 0])  # vertical (positive = looking up)
        yaw = float(euler[1, 0])    # horizontal (positive = looking right)

        return GazeResult(pitch=pitch, yaw=yaw, valid=True)

    def _estimate_mlp(self, landmarks: np.ndarray) -> GazeResult:
        """Phase 2: MLP model inference.

        Input: 8 normalized coordinates (4 iris + 4 eye corners).
        Output: pitch and yaw in degrees.

        TODO: Implement after training the MLP on MPIIGaze.
        """
        # Extract iris and eye corner coordinates
        # left_iris_center = landmarks[IRIS_LANDMARKS["left_iris"]].mean(axis=0)[:2]
        # right_iris_center = landmarks[IRIS_LANDMARKS["right_iris"]].mean(axis=0)[:2]
        # features = np.concatenate([...])
        # pitch, yaw = self._model.predict(features)
        raise NotImplementedError("MLP model not yet trained. Use head pose stub.")

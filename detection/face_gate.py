"""Face Gate — MediaPipe face presence and identity verification.

Uses the MediaPipe Tasks API (mp.tasks.python.vision.FaceLandmarker)
which provides 478 facial landmarks per detected face.

Gate logic (from implementation plan):
- No face detected for > 5 seconds → NO_FACE flag
- Multiple faces detected → MULTIPLE_PERSONS flag
- Face consistency: cosine similarity vs reference < 0.7 → IDENTITY_MISMATCH
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
import structlog

from mediapipe.tasks.python import BaseOptions, vision

logger = structlog.get_logger()

# Path to face landmarker model (relative to project root)
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
_FACE_LANDMARKER_PATH = os.path.join(_MODEL_DIR, "face_landmarker.task")


@dataclass
class FaceGateResult:
    """Result from face gate processing."""
    face_detected: bool = False
    face_count: int = 0
    landmarks: Optional[np.ndarray] = None  # 478 landmarks if detected
    no_face_duration: float = 0.0
    identity_match_score: float = 1.0
    flags: list[str] = field(default_factory=list)


class FaceGate:
    """MediaPipe-based face detection and identity verification gate.

    Every frame passes through this gate before any ML inference.
    If the gate fails, ML inference is skipped and the event is logged directly.

    Uses the modern mp.tasks.python.vision.FaceLandmarker API which
    provides 478 facial landmarks including iris for gaze estimation.
    """

    def __init__(
        self,
        no_face_timeout: float = 5.0,
        identity_threshold: float = 0.7,
        model_path: str = _FACE_LANDMARKER_PATH,
    ):
        self.no_face_timeout = no_face_timeout
        self.identity_threshold = identity_threshold

        # Initialize MediaPipe FaceLandmarker (Tasks API)
        self._landmarker = None
        try:
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                num_faces=2,  # Detect up to 2 for multi-person check
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
                running_mode=vision.RunningMode.IMAGE,
            )
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
            logger.info("face_gate_initialized", backend="mediapipe_tasks_landmarker")
        except Exception as e:
            logger.warning(
                "face_gate_fallback",
                reason=str(e),
                msg="FaceLandmarker unavailable, using OpenCV cascade fallback",
            )
            self._cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )

        # State tracking
        self._last_face_seen: float = time.time()
        self._reference_embedding: Optional[np.ndarray] = None
        self._no_face_flagged: bool = False

    def set_reference_face(self, frame: np.ndarray) -> bool:
        """Capture reference face embedding at session start.

        Args:
            frame: BGR image from webcam.

        Returns:
            True if reference was captured successfully.
        """
        result = self._process_frame(frame)
        if result.face_detected and result.landmarks is not None:
            self._reference_embedding = self._compute_face_embedding(result.landmarks)
            logger.info("reference_face_captured")
            return True
        logger.warning("reference_face_capture_failed")
        return False

    def process(self, frame: np.ndarray) -> FaceGateResult:
        """Process a frame through the face gate.

        Args:
            frame: BGR image from webcam.

        Returns:
            FaceGateResult with detection status and any flags.
        """
        result = self._process_frame(frame)
        now = time.time()

        # No face tracking
        if result.face_detected:
            self._last_face_seen = now
            self._no_face_flagged = False
        else:
            result.no_face_duration = now - self._last_face_seen
            if result.no_face_duration > self.no_face_timeout and not self._no_face_flagged:
                result.flags.append("NO_FACE")
                self._no_face_flagged = True
                logger.warning(
                    "no_face_detected",
                    duration=round(result.no_face_duration, 1),
                )

        # Multiple faces check
        if result.face_count > 1:
            result.flags.append("MULTIPLE_PERSONS")
            logger.warning("multiple_faces_detected", count=result.face_count)

        # Identity consistency check
        if (
            result.face_detected
            and self._reference_embedding is not None
            and result.landmarks is not None
        ):
            current_embedding = self._compute_face_embedding(result.landmarks)
            score = self._cosine_similarity(
                self._reference_embedding, current_embedding
            )
            result.identity_match_score = score
            if score < self.identity_threshold:
                result.flags.append("IDENTITY_MISMATCH")
                logger.warning("identity_mismatch", score=round(score, 3))

        return result

    def _process_frame(self, frame: np.ndarray) -> FaceGateResult:
        """Run face detection on a frame.

        Uses MediaPipe FaceLandmarker (Tasks API) for full 478-landmark
        extraction, or falls back to OpenCV cascade for basic detection.
        """
        result = FaceGateResult()

        if self._landmarker is not None:
            # ── MediaPipe Tasks API path ──
            # Convert BGR → RGB for MediaPipe
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            detection_result = self._landmarker.detect(mp_image)

            if detection_result.face_landmarks:
                result.face_count = len(detection_result.face_landmarks)
                result.face_detected = True

                # Extract 478 landmarks from the primary (first) face
                face_lms = detection_result.face_landmarks[0]
                landmarks = np.array(
                    [[lm.x, lm.y, lm.z] for lm in face_lms],
                    dtype=np.float32,
                )
                result.landmarks = landmarks
        else:
            # ── OpenCV cascade fallback ── (no landmarks, basic detection only)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._cascade.detectMultiScale(gray, 1.3, 5)
            result.face_count = len(faces)
            result.face_detected = result.face_count > 0

        return result

    def _compute_face_embedding(self, landmarks: np.ndarray) -> np.ndarray:
        """Compute a simple geometric face embedding from landmarks.

        Uses distances between key facial landmarks as a fingerprint.
        This is a lightweight alternative to FaceNet/InsightFace for
        identity consistency checks (not full face recognition).
        """
        # Key landmark indices (MediaPipe Face Mesh 478 landmarks)
        key_indices = [
            1,    # Nose tip
            33,   # Left eye inner corner
            263,  # Right eye inner corner
            61,   # Left mouth corner
            291,  # Right mouth corner
            199,  # Chin
            10,   # Forehead
            152,  # Lower jaw
        ]
        key_points = landmarks[key_indices]

        # Compute pairwise distances as embedding
        diffs = key_points[:, None, :] - key_points[None, :, :]
        distances = np.linalg.norm(diffs, axis=-1)

        # Normalize by inter-eye distance for scale invariance
        inter_eye = np.linalg.norm(landmarks[33] - landmarks[263])
        if inter_eye > 0:
            distances /= inter_eye

        # Flatten upper triangle as embedding
        upper_tri = distances[np.triu_indices(len(key_indices), k=1)]
        return upper_tri.astype(np.float32)

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def close(self):
        """Release MediaPipe resources."""
        if self._landmarker is not None:
            self._landmarker.close()

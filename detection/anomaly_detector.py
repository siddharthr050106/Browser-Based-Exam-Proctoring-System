"""Anomaly Detector — decides if gaze pattern is suspicious.

PHASE 1 (STUB): Simple threshold-based rule detection.
- Head yaw > 30° → suspicious
- Head pitch > 20° → suspicious
- Sustained for > 5 seconds → GAZE_ANOMALY flag

PHASE 2 (REAL): One-Class SVM or GMM trained per session.
- 3-minute calibration phase learns "normal" cluster
- Gaze outside cluster > 5 consecutive seconds → GAZE_ANOMALY

The interface: detect(pitch, yaw) → AnomalyResult
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass
class AnomalyResult:
    """Result from anomaly detection."""
    is_anomalous: bool = False
    anomaly_score: float = 0.0  # 0.0 = normal, 1.0 = definitely anomalous
    sustained_duration: float = 0.0  # How long the anomaly has been active
    is_calibrating: bool = False
    flags: list[str] = field(default_factory=list)


class AnomalyDetector:
    """Temporal anomaly detector for gaze patterns.

    Phase 1: Threshold-based (yaw > 30°, pitch > 20°, sustained > 5s).
    Phase 2: One-Class SVM with per-session calibration.
    """

    def __init__(
        self,
        yaw_threshold: float = 30.0,
        pitch_threshold: float = 20.0,
        anomaly_duration_threshold: float = 5.0,
        calibration_duration: float = 180.0,  # 3 minutes
    ):
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.anomaly_duration_threshold = anomaly_duration_threshold
        self.calibration_duration = calibration_duration

        # State
        self._anomaly_start: Optional[float] = None
        self._session_start: Optional[float] = None
        self._is_calibrating: bool = False

        # Phase 2: calibration data
        self._calibration_data: list[tuple[float, float]] = []
        self._svm_model = None  # Will be One-Class SVM in Phase 2

        # TODO Phase 2: These will be set by the FL global model
        self._global_mean_yaw: float = 0.0
        self._global_var_yaw: float = 15.0
        self._global_mean_pitch: float = 0.0
        self._global_var_pitch: float = 10.0

    def start_session(self) -> None:
        """Initialize for a new exam session."""
        self._session_start = time.time()
        self._is_calibrating = True
        self._calibration_data = []
        self._anomaly_start = None
        logger.info("anomaly_detector_session_started")

    def detect(self, pitch: float, yaw: float) -> AnomalyResult:
        """Analyze a gaze data point for anomalies.

        Args:
            pitch: Vertical gaze angle in degrees.
            yaw: Horizontal gaze angle in degrees.

        Returns:
            AnomalyResult with anomaly status and score.
        """
        now = time.time()
        result = AnomalyResult()

        # Check if still in calibration phase
        if self._session_start and self._is_calibrating:
            elapsed = now - self._session_start
            if elapsed < self.calibration_duration:
                self._calibration_data.append((pitch, yaw))
                result.is_calibrating = True
                return result
            else:
                self._finish_calibration()

        # Phase 1: Threshold-based detection
        score = self._compute_anomaly_score(pitch, yaw)
        result.anomaly_score = score

        if score > 0.5:
            # Track sustained anomaly
            if self._anomaly_start is None:
                self._anomaly_start = now

            result.sustained_duration = now - self._anomaly_start

            if result.sustained_duration > self.anomaly_duration_threshold:
                result.is_anomalous = True
                result.flags.append("GAZE_ANOMALY")
                logger.warning(
                    "gaze_anomaly",
                    score=round(score, 2),
                    duration=round(result.sustained_duration, 1),
                    pitch=round(pitch, 1),
                    yaw=round(yaw, 1),
                )
        else:
            self._anomaly_start = None

        return result

    def _compute_anomaly_score(self, pitch: float, yaw: float) -> float:
        """Compute anomaly score based on thresholds.

        Phase 1: Simple threshold ratio.
        Phase 2: Distance from One-Class SVM decision boundary.
        """
        # Normalize deviations by thresholds
        yaw_deviation = abs(yaw) / self.yaw_threshold
        pitch_deviation = abs(pitch) / self.pitch_threshold

        # Combined score (max of the two, capped at 1.0)
        score = min(1.0, max(yaw_deviation, pitch_deviation))
        return score

    def _finish_calibration(self) -> None:
        """End calibration phase and build the anomaly model.

        Phase 1: Just computes mean/std of calibration data for reference.
        Phase 2: Trains a One-Class SVM on the calibration data.
        """
        self._is_calibrating = False

        if len(self._calibration_data) < 10:
            logger.warning("calibration_insufficient_data", count=len(self._calibration_data))
            return

        data = np.array(self._calibration_data)
        mean_pitch, mean_yaw = data.mean(axis=0)
        std_pitch, std_yaw = data.std(axis=0)

        logger.info(
            "calibration_complete",
            samples=len(self._calibration_data),
            mean_pitch=round(mean_pitch, 2),
            mean_yaw=round(mean_yaw, 2),
            std_pitch=round(std_pitch, 2),
            std_yaw=round(std_yaw, 2),
        )

        # TODO Phase 2: Train One-Class SVM here
        # from sklearn.svm import OneClassSVM
        # self._svm_model = OneClassSVM(kernel='rbf', nu=0.1)
        # self._svm_model.fit(data)

    def get_boundary_params(self) -> dict:
        """Export boundary parameters for FL aggregation.

        This is the "micro-payload" sent to the FL server:
        just 4-6 numbers representing the normal gaze boundary.
        """
        if len(self._calibration_data) < 10:
            return {}

        data = np.array(self._calibration_data)
        return {
            "mean_yaw": float(data[:, 1].mean()),
            "var_yaw": float(data[:, 1].var()),
            "mean_pitch": float(data[:, 0].mean()),
            "var_pitch": float(data[:, 0].var()),
            "sample_count": len(self._calibration_data),
        }

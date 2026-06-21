"""Detection Pipeline — orchestrates all detectors.

Runs: face_gate → yolo → background → gaze → anomaly → rule_engine.
Manages frame rate throttling and coordinates output signals.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import structlog

from detection.face_gate import FaceGate
from detection.yolo_detector import YoloDetector
from detection.background_monitor import BackgroundMonitor
from detection.gaze_estimator import GazeEstimator
from detection.anomaly_detector import AnomalyDetector
from detection.audio_detector import AudioDetector
from detection.rule_engine import RuleEngine, DetectionSignal

logger = structlog.get_logger()


class DetectionPipeline:
    """Main detection orchestrator.

    Receives frames from the client, runs all detectors,
    and outputs detection signals via the rule engine.
    """

    def __init__(self, config: dict = None):
        cfg = config or {}
        self.face_gate = FaceGate(
            no_face_timeout=cfg.get("no_face_timeout", 5.0),
            identity_threshold=cfg.get("identity_threshold", 0.7),
        )
        self.yolo = YoloDetector(
            confidence_threshold=cfg.get("yolo_confidence", 0.6),
            phone_consecutive_threshold=cfg.get("phone_consecutive", 2),
            person_consecutive_threshold=cfg.get("person_consecutive", 3),
        )
        self.background = BackgroundMonitor(
            ssim_threshold=cfg.get("ssim_threshold", 0.75),
            check_interval_minutes=cfg.get("bg_interval_min", 10),
        )
        self.gaze = GazeEstimator(
            frame_width=cfg.get("frame_width", 640),
            frame_height=cfg.get("frame_height", 480),
        )
        self.anomaly = AnomalyDetector(
            yaw_threshold=cfg.get("yaw_threshold", 30.0),
            pitch_threshold=cfg.get("pitch_threshold", 20.0),
            anomaly_duration_threshold=cfg.get("anomaly_duration", 5.0),
        )
        self.rules = RuleEngine(
            tab_switch_flag_count=cfg.get("tab_switch_count", 3),
            tab_switch_window_seconds=cfg.get("tab_switch_window", 120.0),
        )
        self.audio = AudioDetector()
        self._frame_count = 0
        self._yolo_interval = 1  # Run YOLO every frame (browser sends at ~0.5fps)
        self._last_gaze = None  # Stores last gaze data for the worker to publish

    def start_session(self, first_frame: np.ndarray) -> None:
        """Initialize all detectors for a new session."""
        self.face_gate.set_reference_face(first_frame)
        self.background.force_reference_update(first_frame)
        self.anomaly.start_session()
        self.yolo.reset_streaks()
        self._frame_count = 0
        logger.info("detection_pipeline_started")

    def process_frame(self, frame: np.ndarray) -> list[DetectionSignal]:
        """Process a single video frame through all detectors.

        Returns a list of detection signals (may be empty if nothing detected).
        """
        self._frame_count += 1
        signals: list[DetectionSignal] = []

        # 1) Face gate (every frame)
        fg = self.face_gate.process(frame)
        if fg.flags:
            signals.extend(self.rules.process_face_gate(fg.flags))

        # 2) YOLO (throttled to ~5fps if camera is 30fps)
        if self._frame_count % self._yolo_interval == 0:
            yr = self.yolo.process(frame)
            if yr.flags:
                meta = {}
                if yr.phone_bbox:
                    meta["phone_bbox"] = yr.phone_bbox
                if yr.person_bboxes:
                    meta["person_bboxes"] = yr.person_bboxes
                signals.extend(self.rules.process_yolo(yr.flags, meta))

        # 3) Background (adds frame to buffer, checks interval)
        self.background.add_frame(frame)
        bg = self.background.check()
        if bg and bg.flags:
            signals.extend(self.rules.process_background(
                bg.flags, bg.ssim_score,
            ))

        # 4) Gaze + Anomaly (only if face detected with landmarks)
        self._last_gaze = None
        if fg.face_detected and fg.landmarks is not None:
            gz = self.gaze.estimate(fg.landmarks)
            if gz.valid:
                ar = self.anomaly.detect(gz.pitch, gz.yaw)
                self._last_gaze = {
                    "yaw": gz.yaw,
                    "pitch": gz.pitch,
                    "anomaly_score": ar.anomaly_score,
                }
                # Gaze anomaly alerting disabled — data still collected for timeline
                # if ar.flags:
                #     signals.extend(self.rules.process_gaze_anomaly(
                #         ar.flags, ar.anomaly_score,
                #     ))

        # 5) Check composite critical for each new FLAG
        for sig in list(signals):
            composite = self.rules.check_composite_critical(sig)
            if composite:
                signals.append(composite)

        return signals

    def process_browser_event(self, event_type: str) -> DetectionSignal:
        """Process a browser-level event (tab switch, blur, fullscreen exit)."""
        return self.rules.process_tab_switch(event_type)

    def process_audio(self, pcm_int16: np.ndarray) -> list[DetectionSignal]:
        """Process an audio chunk through the CNN."""
        signals = []
        ar = self.audio.detect(pcm_int16)
        
        if ar.flags:
            meta = {"sustained_windows": ar.sustained_windows}
            signals.extend(self.rules.process_audio(ar.flags, ar.confidence, meta))
            
        # Check composite critical for audio flags too
        for sig in list(signals):
            composite = self.rules.check_composite_critical(sig)
            if composite:
                signals.append(composite)
                
        return signals, ar

    def close(self) -> None:
        """Release resources."""
        self.face_gate.close()
        logger.info("detection_pipeline_closed")

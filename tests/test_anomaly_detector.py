"""Tests for the anomaly detector."""

import time
from detection.anomaly_detector import AnomalyDetector


def test_below_threshold_not_anomalous():
    """Gaze within thresholds should not be flagged."""
    detector = AnomalyDetector(yaw_threshold=30, pitch_threshold=20)
    result = detector.detect(pitch=5.0, yaw=10.0)
    assert not result.is_anomalous
    assert result.anomaly_score < 0.5


def test_above_threshold_scores_high():
    """Gaze beyond thresholds should have high anomaly score."""
    detector = AnomalyDetector(yaw_threshold=30, pitch_threshold=20)
    result = detector.detect(pitch=25.0, yaw=35.0)
    assert result.anomaly_score > 0.5


def test_sustained_anomaly_flags():
    """Sustained anomaly beyond duration threshold should flag."""
    detector = AnomalyDetector(
        yaw_threshold=30, pitch_threshold=20,
        anomaly_duration_threshold=0.01,  # Very short for testing
        calibration_duration=0,  # No calibration
    )
    detector._is_calibrating = False
    detector._anomaly_start = time.time() - 10  # 10 seconds ago

    result = detector.detect(pitch=25.0, yaw=40.0)
    assert result.is_anomalous
    assert "GAZE_ANOMALY" in result.flags


def test_calibration_phase():
    """During calibration, no anomalies should be detected."""
    detector = AnomalyDetector(calibration_duration=300)
    detector.start_session()
    result = detector.detect(pitch=50.0, yaw=60.0)  # extreme values
    assert result.is_calibrating
    assert not result.is_anomalous


def test_anomaly_score_computation():
    """Score should be max(yaw_ratio, pitch_ratio), capped at 1.0."""
    detector = AnomalyDetector(yaw_threshold=30, pitch_threshold=20)
    detector._is_calibrating = False
    # yaw = 45 → ratio = 1.5 → capped at 1.0
    result = detector.detect(pitch=0, yaw=45)
    assert result.anomaly_score == 1.0


def test_boundary_params_export():
    """FL micro-payload export should return correct format."""
    detector = AnomalyDetector()
    detector._calibration_data = [(5.0, 10.0)] * 20  # 20 samples
    params = detector.get_boundary_params()
    assert "mean_yaw" in params
    assert "var_yaw" in params
    assert "mean_pitch" in params
    assert "var_pitch" in params
    assert params["sample_count"] == 20


def test_boundary_params_empty():
    """FL export with insufficient data should return empty dict."""
    detector = AnomalyDetector()
    params = detector.get_boundary_params()
    assert params == {}

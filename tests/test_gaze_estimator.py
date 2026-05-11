"""Tests for the gaze estimator."""

import numpy as np
from detection.gaze_estimator import GazeEstimator, GazeResult


def test_invalid_landmarks():
    """None or short landmarks should return invalid result."""
    est = GazeEstimator()
    result = est.estimate(None)
    assert not result.valid

    result = est.estimate(np.zeros((10, 3)))
    assert not result.valid


def test_valid_landmarks_returns_result():
    """Valid 478-landmark array should produce a result."""
    est = GazeEstimator(frame_width=640, frame_height=480)
    # Create normalized landmarks (0-1 range)
    landmarks = np.random.rand(478, 3).astype(np.float32)
    # Ensure landmarks are in reasonable range for solvePnP
    landmarks[:, :2] = np.clip(landmarks[:, :2], 0.1, 0.9)
    result = est.estimate(landmarks)
    # Result may or may not be valid depending on solvePnP convergence
    assert isinstance(result, GazeResult)


def test_default_result():
    """Default GazeResult should have zero pitch/yaw and invalid flag."""
    r = GazeResult()
    assert r.pitch == 0.0
    assert r.yaw == 0.0
    assert r.valid is False


def test_mlp_not_implemented():
    """MLP estimation should raise NotImplementedError."""
    est = GazeEstimator()
    est._use_mlp = True
    try:
        est._estimate_mlp(np.zeros((478, 3)))
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        pass

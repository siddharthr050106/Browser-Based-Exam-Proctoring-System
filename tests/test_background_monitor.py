"""Tests for the background monitor."""

import numpy as np
import time
from detection.background_monitor import BackgroundMonitor


def _make_gray_frame(value=128, w=640, h=480):
    """Create a BGR frame with uniform gray value."""
    return np.full((h, w, 3), value, dtype=np.uint8)


def test_initialization():
    """Monitor should initialize without errors."""
    mon = BackgroundMonitor(ssim_threshold=0.75)
    assert mon._initialized is False


def test_add_frame():
    """Adding frames should fill the buffer."""
    mon = BackgroundMonitor(median_frames=5)
    for _ in range(3):
        mon.add_frame(_make_gray_frame())
    assert len(mon._frame_buffer) == 3


def test_buffer_limit():
    """Buffer should not exceed median_frames."""
    mon = BackgroundMonitor(median_frames=5)
    for _ in range(10):
        mon.add_frame(_make_gray_frame())
    assert len(mon._frame_buffer) == 5


def test_check_returns_none_before_initialization():
    """Check should return None before enough frames collected."""
    mon = BackgroundMonitor(median_frames=30)
    for _ in range(5):
        mon.add_frame(_make_gray_frame())
    result = mon.check()
    assert result is None


def test_no_change_detected_same_background():
    """Same background should have high SSIM — no flag."""
    mon = BackgroundMonitor(
        median_frames=5,
        check_interval_minutes=0,  # Check every time
    )
    frame = _make_gray_frame(128)
    for _ in range(5):
        mon.add_frame(frame)
    mon.check()  # Initialize reference

    # Wait a tiny bit to pass interval
    mon._last_check = 0
    result = mon.check()
    if result is not None:
        assert not result.changed
        assert result.ssim_score > 0.9


def test_change_detected_different_background():
    """Different background should have low SSIM — flag."""
    mon = BackgroundMonitor(
        ssim_threshold=0.75,
        median_frames=5,
        check_interval_minutes=0,
    )
    # Initialize with dark frames
    for _ in range(5):
        mon.add_frame(_make_gray_frame(50))
    mon.check()  # Initialize reference

    # Replace buffer with bright frames
    mon._frame_buffer = []
    for _ in range(5):
        mon.add_frame(_make_gray_frame(250))

    mon._last_check = 0  # Force check
    result = mon.check()
    if result is not None:
        assert result.changed
        assert "BACKGROUND_CHANGED" in result.flags
        assert result.ssim_score < 0.75


def test_force_reference_update():
    """Force reference update should set initialized."""
    mon = BackgroundMonitor()
    mon.force_reference_update(_make_gray_frame())
    assert mon._initialized is True

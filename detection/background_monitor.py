"""Background Monitor — SSIM-based background change detection.

Rules (from implementation plan):
- Every 10 minutes, capture reference background via running median (30 frames)
- Compare current background estimate vs reference using SSIM
- SSIM < 0.75 → BACKGROUND_CHANGED flag with before/after thumbnails
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
import structlog
from skimage.metrics import structural_similarity as ssim

logger = structlog.get_logger()


@dataclass
class BackgroundResult:
    """Result from background monitoring."""
    ssim_score: float = 1.0
    changed: bool = False
    reference_thumbnail: Optional[np.ndarray] = None
    current_thumbnail: Optional[np.ndarray] = None
    flags: list[str] = field(default_factory=list)


class BackgroundMonitor:
    """SSIM-based background drift detector.

    Lightweight: runs once per 10 minutes, not per frame.
    Uses running median over 30 frames to remove the student from
    the background estimate.
    """

    def __init__(
        self,
        ssim_threshold: float = 0.75,
        check_interval_minutes: int = 10,
        median_frames: int = 30,
        thumbnail_size: tuple[int, int] = (160, 120),
    ):
        self.ssim_threshold = ssim_threshold
        self.check_interval = check_interval_minutes * 60  # seconds
        self.median_frames = median_frames
        self.thumbnail_size = thumbnail_size

        # State
        self._reference_bg: Optional[np.ndarray] = None
        self._frame_buffer: list[np.ndarray] = []
        self._last_check: float = 0.0
        self._initialized: bool = False

    def add_frame(self, frame: np.ndarray) -> None:
        """Add a frame to the running buffer for background estimation.

        Call this on every processed frame. The buffer maintains the last
        N frames for computing the running median.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, self.thumbnail_size)

        self._frame_buffer.append(resized)
        if len(self._frame_buffer) > self.median_frames:
            self._frame_buffer.pop(0)

    def check(self) -> Optional[BackgroundResult]:
        """Check for background changes if the interval has elapsed.

        Returns:
            BackgroundResult if a check was performed, None if skipped.
        """
        now = time.time()

        # Not enough frames yet
        if len(self._frame_buffer) < self.median_frames:
            return None

        # Compute current background estimate
        current_bg = np.median(
            np.stack(self._frame_buffer), axis=0
        ).astype(np.uint8)

        # Initialize reference on first check
        if not self._initialized:
            self._reference_bg = current_bg.copy()
            self._last_check = now
            self._initialized = True
            logger.info("background_reference_initialized")
            return None

        # Check interval
        if now - self._last_check < self.check_interval:
            return None

        self._last_check = now

        # Compute SSIM
        score = ssim(self._reference_bg, current_bg)
        result = BackgroundResult(ssim_score=score)

        if score < self.ssim_threshold:
            result.changed = True
            result.flags.append("BACKGROUND_CHANGED")
            result.reference_thumbnail = self._reference_bg.copy()
            result.current_thumbnail = current_bg.copy()
            logger.warning("background_changed", ssim=round(score, 3))

            # Update reference to current (avoid re-flagging same change)
            self._reference_bg = current_bg.copy()
        else:
            logger.debug("background_check_ok", ssim=round(score, 3))

        return result

    def force_reference_update(self, frame: np.ndarray) -> None:
        """Force update the reference background (e.g., on session start)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._reference_bg = cv2.resize(gray, self.thumbnail_size)
        self._initialized = True
        self._last_check = time.time()
        logger.info("background_reference_forced")

"""Rule Engine — central escalation logic.

Collects signals from all detectors and applies the escalation tier matrix.

Escalation Matrix:
- Single tab switch → INFO
- 3+ tab switches in 2 min → FLAG
- Phone detected (2 consecutive) → FLAG
- Multiple persons (3 consecutive) → FLAG  
- Background change → FLAG
- Identity mismatch → CRITICAL
- Gaze anomaly > 0.7 → FLAG
- Any FLAG → 30s clip captured
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(str, Enum):
    INFO = "info"
    WARNING = "warning"
    FLAG = "flag"
    CRITICAL = "critical"


@dataclass
class DetectionSignal:
    """A detection signal from any detector."""
    event_type: str
    tier: Tier
    confidence: Optional[float] = None
    metadata: Optional[dict] = None
    timestamp: float = field(default_factory=time.time)
    requires_clip: bool = False


class RuleEngine:
    """Central escalation engine."""

    def __init__(
        self,
        tab_switch_flag_count: int = 3,
        tab_switch_window_seconds: float = 120.0,
    ):
        self.tab_switch_flag_count = tab_switch_flag_count
        self.tab_switch_window = tab_switch_window_seconds
        self._tab_switches: deque[float] = deque()
        self._recent_flags: deque[tuple[str, float]] = deque()
        self._recent_flags_window: float = 60.0

    def process_face_gate(self, flags: list[str]) -> list[DetectionSignal]:
        signals = []
        for flag in flags:
            if flag == "NO_FACE":
                signals.append(DetectionSignal(event_type="no_face", tier=Tier.FLAG, requires_clip=True))
            elif flag == "MULTIPLE_PERSONS":
                signals.append(DetectionSignal(event_type="multiple_persons", tier=Tier.FLAG, requires_clip=True))
            elif flag == "IDENTITY_MISMATCH":
                signals.append(DetectionSignal(event_type="identity_mismatch", tier=Tier.CRITICAL, requires_clip=True))
        return signals

    def process_yolo(self, flags: list[str], metadata: dict = None) -> list[DetectionSignal]:
        signals = []
        for flag in flags:
            if flag == "PHONE_DETECTED":
                signals.append(DetectionSignal(event_type="phone_detected", tier=Tier.FLAG, metadata=metadata, requires_clip=True))
            elif flag == "MULTIPLE_PERSONS":
                signals.append(DetectionSignal(event_type="multiple_persons", tier=Tier.FLAG, metadata=metadata, requires_clip=True))
        return signals

    def process_background(self, flags: list[str], ssim_score: float = None, metadata: dict = None) -> list[DetectionSignal]:
        signals = []
        for flag in flags:
            if flag == "BACKGROUND_CHANGED":
                signals.append(DetectionSignal(event_type="background_changed", tier=Tier.FLAG, confidence=ssim_score, metadata=metadata, requires_clip=True))
        return signals

    def process_gaze_anomaly(self, flags: list[str], score: float = 0.0) -> list[DetectionSignal]:
        signals = []
        for flag in flags:
            if flag == "GAZE_ANOMALY":
                tier = Tier.FLAG if score > 0.7 else Tier.WARNING
                signals.append(DetectionSignal(event_type="gaze_anomaly", tier=tier, confidence=score, requires_clip=(tier == Tier.FLAG)))
        return signals

    def process_tab_switch(self, event_type: str = "tab_switch") -> DetectionSignal:
        now = time.time()
        self._tab_switches.append(now)
        cutoff = now - self.tab_switch_window
        while self._tab_switches and self._tab_switches[0] < cutoff:
            self._tab_switches.popleft()
        count = len(self._tab_switches)

        if count >= self.tab_switch_flag_count:
            return DetectionSignal(event_type=event_type, tier=Tier.FLAG, metadata={"count_in_window": count}, requires_clip=True)
        elif count >= 2:
            return DetectionSignal(event_type=event_type, tier=Tier.WARNING, metadata={"count_in_window": count})
        else:
            return DetectionSignal(event_type=event_type, tier=Tier.INFO, metadata={"count_in_window": count})

    def check_composite_critical(self, signal: DetectionSignal) -> Optional[DetectionSignal]:
        now = time.time()
        if signal.tier in (Tier.FLAG, Tier.CRITICAL):
            self._recent_flags.append((signal.event_type, now))
        cutoff = now - self._recent_flags_window
        while self._recent_flags and self._recent_flags[0][1] < cutoff:
            self._recent_flags.popleft()

        recent_types = {f[0] for f in self._recent_flags}
        critical_combo = {"background_changed", "phone_detected", "gaze_anomaly"}
        if len(recent_types & critical_combo) >= 2:
            return DetectionSignal(event_type="composite_critical", tier=Tier.CRITICAL, metadata={"coincident_events": list(recent_types & critical_combo)}, requires_clip=True)
        return None

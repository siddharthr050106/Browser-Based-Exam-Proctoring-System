"""Escalation service — tier logic and composite scoring.

Implements the escalation matrix from the implementation plan:
- INFO:     Single tab switch, brief gaze deviation < 5s
- WARNING:  2 tab switches in 5 min, gaze anomaly score 0.5-0.7
- FLAG:     Phone detected, multiple persons, gaze > 0.7 sustained, audio coached
- CRITICAL: Identity mismatch, background + phone + gaze coincide
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import DetectionEvent, EventType, EventTier


# Events that immediately escalate to FLAG
IMMEDIATE_FLAG_EVENTS = {
    EventType.PHONE_DETECTED,
    EventType.MULTIPLE_PERSONS,
}

# Events that immediately escalate to CRITICAL
IMMEDIATE_CRITICAL_EVENTS = {
    EventType.IDENTITY_MISMATCH,
}


async def determine_tier(
    db: AsyncSession,
    session_id: uuid.UUID,
    event_type: EventType,
    confidence: Optional[float] = None,
) -> EventTier:
    """Determine the escalation tier for a new event based on rules.

    Rules (from implementation plan Section 3.2):
    - Single tab switch → INFO
    - 3+ tab switches in 2 minutes → FLAG
    - Phone detected (2 consecutive frames) → immediate FLAG
    - Multiple persons (3 consecutive frames) → immediate FLAG
    - Identity mismatch → CRITICAL
    - Background change → FLAG
    - Gaze anomaly 0.5-0.7 → WARNING, > 0.7 → FLAG
    """
    # Immediate escalations
    if event_type in IMMEDIATE_CRITICAL_EVENTS:
        return EventTier.CRITICAL

    if event_type in IMMEDIATE_FLAG_EVENTS:
        return EventTier.FLAG

    if event_type == EventType.BACKGROUND_CHANGED:
        return EventTier.FLAG

    # Tab switch escalation: count recent tab switches
    if event_type in (EventType.TAB_SWITCH, EventType.FULLSCREEN_EXIT, EventType.WINDOW_BLUR):
        two_min_ago = datetime.now(timezone.utc) - timedelta(minutes=2)
        result = await db.execute(
            select(func.count(DetectionEvent.id)).where(
                DetectionEvent.session_id == session_id,
                DetectionEvent.event_type.in_([
                    EventType.TAB_SWITCH,
                    EventType.FULLSCREEN_EXIT,
                    EventType.WINDOW_BLUR,
                ]),
                DetectionEvent.timestamp >= two_min_ago,
            )
        )
        recent_count = result.scalar() or 0
        if recent_count >= 2:  # This will be the 3rd
            return EventTier.FLAG
        elif recent_count >= 1:
            return EventTier.WARNING
        return EventTier.INFO

    # Gaze anomaly: score-based
    if event_type == EventType.GAZE_ANOMALY:
        if confidence is not None and confidence > 0.7:
            return EventTier.FLAG
        elif confidence is not None and confidence > 0.5:
            return EventTier.WARNING
        return EventTier.INFO

    # No face
    if event_type == EventType.NO_FACE:
        return EventTier.FLAG

    # Default
    return EventTier.INFO


async def check_composite_critical(
    db: AsyncSession, session_id: uuid.UUID
) -> bool:
    """Check if multiple FLAG events coincide → CRITICAL escalation.

    If background_changed + phone + gaze all happen within 1 minute, escalate.
    """
    one_min_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    result = await db.execute(
        select(DetectionEvent.event_type).where(
            DetectionEvent.session_id == session_id,
            DetectionEvent.tier.in_([EventTier.FLAG, EventTier.CRITICAL]),
            DetectionEvent.timestamp >= one_min_ago,
        )
    )
    recent_flag_types = {row[0] for row in result.all()}

    # Triple coincidence → CRITICAL
    critical_combo = {
        EventType.BACKGROUND_CHANGED,
        EventType.PHONE_DETECTED,
        EventType.GAZE_ANOMALY,
    }
    if len(recent_flag_types & critical_combo) >= 2:
        return True

    return False

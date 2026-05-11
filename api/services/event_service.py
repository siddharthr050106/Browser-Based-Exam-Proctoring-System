"""Event service — business logic for detection events and gaze snapshots."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import DetectionEvent
from api.models.gaze_snapshot import GazeSnapshot
from api.schemas.event import EventCreate, GazeSnapshotCreate


async def create_event(db: AsyncSession, data: EventCreate) -> DetectionEvent:
    """Record a new detection event."""
    event = DetectionEvent(
        session_id=data.session_id,
        event_type=data.event_type,
        tier=data.tier,
        confidence=data.confidence,
        metadata_json=data.metadata_json,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


async def get_events_for_session(
    db: AsyncSession, session_id: uuid.UUID
) -> list[DetectionEvent]:
    """Retrieve all detection events for a session."""
    result = await db.execute(
        select(DetectionEvent)
        .where(DetectionEvent.session_id == session_id)
        .order_by(DetectionEvent.timestamp.desc())
    )
    return list(result.scalars().all())


async def set_clip_url(
    db: AsyncSession, event_id: uuid.UUID, clip_url: str
) -> DetectionEvent | None:
    """Attach a video clip URL to an existing event."""
    result = await db.execute(
        select(DetectionEvent).where(DetectionEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        return None
    event.clip_url = clip_url
    await db.flush()
    await db.refresh(event)
    return event


async def create_gaze_snapshot(
    db: AsyncSession, data: GazeSnapshotCreate
) -> GazeSnapshot:
    """Record a gaze snapshot for the proctor timeline."""
    snapshot = GazeSnapshot(
        session_id=data.session_id,
        gaze_x=data.gaze_x,
        gaze_y=data.gaze_y,
        head_yaw=data.head_yaw,
        head_pitch=data.head_pitch,
        blink_rate=data.blink_rate,
        anomaly_score=data.anomaly_score,
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


async def get_gaze_snapshots(
    db: AsyncSession, session_id: uuid.UUID
) -> list[GazeSnapshot]:
    """Retrieve all gaze snapshots for a session (proctor timeline)."""
    result = await db.execute(
        select(GazeSnapshot)
        .where(GazeSnapshot.session_id == session_id)
        .order_by(GazeSnapshot.timestamp.asc())
    )
    return list(result.scalars().all())

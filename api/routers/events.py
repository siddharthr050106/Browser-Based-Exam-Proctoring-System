"""Events router — detection event ingestion and retrieval."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.event import (
    EventCreate,
    EventResponse,
    EventListResponse,
    GazeSnapshotCreate,
    GazeSnapshotResponse,
)
from api.services import event_service, escalation_service

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(data: EventCreate, db: AsyncSession = Depends(get_db)):
    """Receive a detection event from the detection worker.

    Automatically determines escalation tier if not specified correctly,
    and checks for composite critical conditions.
    """
    # Auto-determine tier based on escalation rules
    computed_tier = await escalation_service.determine_tier(
        db, data.session_id, data.event_type, data.confidence
    )
    # Use the higher of computed vs submitted tier
    tier_priority = {"info": 0, "warning": 1, "flag": 2, "critical": 3}
    if tier_priority.get(computed_tier.value, 0) > tier_priority.get(data.tier.value, 0):
        data.tier = computed_tier

    event = await event_service.create_event(db, data)

    # Check for composite critical escalation
    if await escalation_service.check_composite_critical(db, data.session_id):
        if data.tier.value != "critical":
            event.tier = "critical"
            await db.flush()
            await db.refresh(event)

    return event


@router.get("/{session_id}", response_model=EventListResponse)
async def list_events(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all detection events for a session."""
    events = await event_service.get_events_for_session(db, session_id)
    return EventListResponse(events=events, total=len(events))


@router.post("/gaze", response_model=GazeSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_gaze_snapshot(
    data: GazeSnapshotCreate, db: AsyncSession = Depends(get_db)
):
    """Record a gaze snapshot for the proctor timeline."""
    snapshot = await event_service.create_gaze_snapshot(db, data)
    return snapshot


@router.get("/gaze/{session_id}", response_model=list[GazeSnapshotResponse])
async def list_gaze_snapshots(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Retrieve gaze snapshots for a session (proctor timeline chart)."""
    return await event_service.get_gaze_snapshots(db, session_id)

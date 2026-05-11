"""Sessions router — exam session lifecycle."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.session import (
    SessionCreate,
    SessionUpdate,
    SessionResponse,
    SessionListResponse,
    SessionWarnRequest,
    SessionTerminateRequest,
    SessionReviewRequest,
)
from api.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    """Start a new exam proctoring session."""
    session = await session_service.create_session(db, data)
    return session


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve session details."""
    session = await session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """End an active exam session."""
    session = await session_service.end_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: uuid.UUID,
    data: SessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update session status or network tier."""
    session = await session_service.update_session(db, session_id, data)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/", response_model=SessionListResponse)
async def list_active_sessions(db: AsyncSession = Depends(get_db)):
    """List all currently active sessions (proctor dashboard)."""
    sessions = await session_service.list_active_sessions(db)
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.post("/{session_id}/warn", response_model=SessionResponse)
async def warn_session(
    session_id: uuid.UUID,
    data: SessionWarnRequest,
    db: AsyncSession = Depends(get_db),
):
    """Proctor issues a warning to the student.

    This triggers:
    1. Records warning_issued_at on the session
    2. Broadcasts to the student via WebSocket to show warning overlay
    3. Student captures 30s clip (20s before + 10s after warning) and uploads it
    """
    session = await session_service.warn_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Broadcast warning to student WebSocket
    from api.routers.ws import broadcast_to_student, broadcast_event
    await broadcast_to_student(session_id, {
        "type": "proctor_warning",
        "message": data.message,
        "timestamp": session.warning_issued_at.isoformat(),
    })
    # Notify proctors too
    await broadcast_event(session_id, {
        "event_type": "proctor_warning_issued",
        "tier": "info",
        "timestamp": session.warning_issued_at.isoformat(),
    })
    return session


@router.post("/{session_id}/terminate", response_model=SessionResponse)
async def terminate_session(
    session_id: uuid.UUID,
    data: SessionTerminateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Proctor terminates the exam after reviewing the warning clip.

    This ends the session immediately and notifies the student.
    """
    session = await session_service.terminate_session(db, session_id, data.reason)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Notify student
    from api.routers.ws import broadcast_to_student, broadcast_event
    await broadcast_to_student(session_id, {
        "type": "session_terminated",
        "reason": data.reason,
        "timestamp": session.end_time.isoformat(),
    })
    # Notify proctors
    await broadcast_event(session_id, {
        "event_type": "session_terminated",
        "tier": "critical",
        "timestamp": session.end_time.isoformat(),
        "metadata_json": {"reason": data.reason},
    })
    return session


@router.post("/{session_id}/review")
async def review_warning(
    session_id: uuid.UUID,
    data: SessionReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """Proctor reviews the warning clip and provides a verdict.

    Verdicts:
    - not_anomaly: dismiss as false positive
    - add_note: flag with observation notes
    - continue_monitoring: keep watching
    """
    session = await session_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    from api.routers.ws import broadcast_event
    await broadcast_event(session_id, {
        "event_type": f"proctor_review_{data.verdict}",
        "tier": "info",
        "metadata_json": {"verdict": data.verdict, "notes": data.notes},
    })
    return {"status": "reviewed", "verdict": data.verdict}

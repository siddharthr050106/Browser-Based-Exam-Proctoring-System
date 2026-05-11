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

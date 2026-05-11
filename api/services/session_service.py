"""Session service — business logic for exam sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.session import ExamSession, SessionStatus
from api.schemas.session import SessionCreate, SessionUpdate


async def create_session(db: AsyncSession, data: SessionCreate) -> ExamSession:
    """Start a new exam session."""
    session = ExamSession(
        student_id=data.student_id,
        exam_id=data.exam_id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> ExamSession | None:
    """Retrieve a session by ID."""
    result = await db.execute(
        select(ExamSession).where(ExamSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def end_session(db: AsyncSession, session_id: uuid.UUID) -> ExamSession | None:
    """End an exam session."""
    session = await get_session(db, session_id)
    if session is None:
        return None
    session.status = SessionStatus.COMPLETED
    session.end_time = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(session)
    return session


async def update_session(
    db: AsyncSession, session_id: uuid.UUID, data: SessionUpdate
) -> ExamSession | None:
    """Update session fields (status, network tier, etc.)."""
    session = await get_session(db, session_id)
    if session is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    await db.flush()
    await db.refresh(session)
    return session


async def list_active_sessions(db: AsyncSession) -> list[ExamSession]:
    """Get all currently active sessions (for proctor dashboard)."""
    result = await db.execute(
        select(ExamSession).where(ExamSession.status == SessionStatus.ACTIVE)
    )
    return list(result.scalars().all())


async def list_sessions_for_exam(
    db: AsyncSession, exam_id: uuid.UUID
) -> list[ExamSession]:
    """Get all sessions for a specific exam."""
    result = await db.execute(
        select(ExamSession).where(ExamSession.exam_id == exam_id)
    )
    return list(result.scalars().all())

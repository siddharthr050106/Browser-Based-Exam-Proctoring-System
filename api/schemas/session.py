"""Pydantic schemas for exam sessions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from api.models.session import SessionStatus, NetworkTier


class SessionCreate(BaseModel):
    student_id: uuid.UUID
    exam_id: uuid.UUID


class SessionUpdate(BaseModel):
    status: Optional[SessionStatus] = None
    network_tier: Optional[NetworkTier] = None
    end_time: Optional[datetime] = None


class SessionResponse(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    exam_id: uuid.UUID
    status: SessionStatus
    network_tier: NetworkTier
    start_time: datetime
    end_time: Optional[datetime] = None
    warning_issued_at: Optional[datetime] = None
    termination_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int


class SessionWarnRequest(BaseModel):
    """Proctor issues a warning to the student."""
    message: Optional[str] = "You have been flagged for suspicious activity. Please comply with exam rules."


class SessionTerminateRequest(BaseModel):
    """Proctor terminates the exam session after reviewing the clip."""
    reason: str


class SessionReviewRequest(BaseModel):
    """Proctor reviews the warning clip and provides a verdict."""
    verdict: str  # "not_anomaly", "add_note", "continue_monitoring"
    notes: Optional[str] = None

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
    current_gear: Optional[int] = None
    trust_score: Optional[float] = None


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
    current_gear: Optional[int] = 1
    last_heartbeat_at: Optional[datetime] = None
    trust_score: Optional[float] = 1.0

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

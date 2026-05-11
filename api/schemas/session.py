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

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int

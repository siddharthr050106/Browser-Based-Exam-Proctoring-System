"""Pydantic schemas for exams."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel


class ExamCreate(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int = 60
    scheduled_at: Optional[datetime] = None
    max_attempts: int = 1
    detection_config: Optional[dict[str, Any]] = None
    fl_enabled: bool = False


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    max_attempts: Optional[int] = None
    is_active: Optional[bool] = None
    detection_config: Optional[dict[str, Any]] = None
    fl_enabled: Optional[bool] = None


class ExamResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    duration_minutes: int
    scheduled_at: Optional[datetime] = None
    max_attempts: int
    is_active: bool
    detection_config: Optional[dict[str, Any]] = None
    fl_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExamListResponse(BaseModel):
    exams: list[ExamResponse]
    total: int

"""Pydantic schemas for detection events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel

from api.models.event import EventType, EventTier


class EventCreate(BaseModel):
    session_id: uuid.UUID
    event_type: EventType
    tier: EventTier
    confidence: Optional[float] = None
    metadata_json: Optional[dict[str, Any]] = None


class EventResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    event_type: EventType
    tier: EventTier
    confidence: Optional[float] = None
    timestamp: datetime
    clip_url: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    events: list[EventResponse]
    total: int


class GazeSnapshotCreate(BaseModel):
    session_id: uuid.UUID
    gaze_x: Optional[float] = None
    gaze_y: Optional[float] = None
    head_yaw: Optional[float] = None
    head_pitch: Optional[float] = None
    blink_rate: Optional[float] = None
    anomaly_score: Optional[float] = None


class GazeSnapshotResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    timestamp: datetime
    gaze_x: Optional[float] = None
    gaze_y: Optional[float] = None
    head_yaw: Optional[float] = None
    head_pitch: Optional[float] = None
    blink_rate: Optional[float] = None
    anomaly_score: Optional[float] = None

    model_config = {"from_attributes": True}

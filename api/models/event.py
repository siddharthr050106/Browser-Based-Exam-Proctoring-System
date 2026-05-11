"""DetectionEvent ORM model — every flag/warning logged here."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class EventType(str, enum.Enum):
    PHONE_DETECTED = "phone_detected"
    MULTIPLE_PERSONS = "multiple_persons"
    NO_FACE = "no_face"
    IDENTITY_MISMATCH = "identity_mismatch"
    BACKGROUND_CHANGED = "background_changed"
    TAB_SWITCH = "tab_switch"
    FULLSCREEN_EXIT = "fullscreen_exit"
    WINDOW_BLUR = "window_blur"
    GAZE_ANOMALY = "gaze_anomaly"
    COACHED_ANSWER = "coached_answer"


class EventTier(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    FLAG = "flag"
    CRITICAL = "critical"


class DetectionEvent(Base):
    __tablename__ = "detection_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exam_sessions.id"), nullable=False, index=True
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    tier: Mapped[EventTier] = mapped_column(
        Enum(EventTier, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    clip_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    session = relationship("ExamSession", back_populates="events")
    review = relationship("ProctorReview", back_populates="event", uselist=False, lazy="selectin")

"""GazeSnapshot ORM model — periodic gaze data for proctor timeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class GazeSnapshot(Base):
    __tablename__ = "gaze_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exam_sessions.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    gaze_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    gaze_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    head_yaw: Mapped[float | None] = mapped_column(Float, nullable=True)
    head_pitch: Mapped[float | None] = mapped_column(Float, nullable=True)
    blink_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    session = relationship("ExamSession", back_populates="gaze_snapshots")

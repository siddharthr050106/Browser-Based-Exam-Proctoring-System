"""ExamSession ORM model — active proctoring sessions."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class NetworkTier(str, enum.Enum):
    TIER_1 = "tier_1"  # >10 Mbps
    TIER_2 = "tier_2"  # 2-10 Mbps
    TIER_3 = "tier_3"  # 0.5-2 Mbps
    TIER_4 = "tier_4"  # <0.5 Mbps


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, values_callable=lambda e: [x.value for x in e]),
        default=SessionStatus.ACTIVE
    )
    network_tier: Mapped[NetworkTier] = mapped_column(
        Enum(NetworkTier, values_callable=lambda e: [x.value for x in e]),
        default=NetworkTier.TIER_1
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warning_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    student = relationship("User", back_populates="sessions", lazy="selectin")
    exam = relationship("Exam", back_populates="sessions", lazy="selectin")
    events = relationship("DetectionEvent", back_populates="session", lazy="selectin")
    gaze_snapshots = relationship("GazeSnapshot", back_populates="session", lazy="selectin")

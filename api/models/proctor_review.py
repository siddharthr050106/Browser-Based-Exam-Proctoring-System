"""ProctorReview ORM model — proctor verdicts on flagged events."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class ReviewVerdict(str, enum.Enum):
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    PENDING = "pending"


class ProctorReview(Base):
    __tablename__ = "proctor_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("detection_events.id"), nullable=False, unique=True
    )
    proctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    verdict: Mapped[ReviewVerdict] = mapped_column(
        Enum(ReviewVerdict, values_callable=lambda e: [x.value for x in e]),
        default=ReviewVerdict.PENDING
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    event = relationship("DetectionEvent", back_populates="review")
    proctor = relationship("User", back_populates="reviews")

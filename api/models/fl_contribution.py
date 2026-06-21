"""FL Contribution Model."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON

from api.database import Base

class FLContribution(Base):
    """Stores local model updates (micro-payloads) from clients for FL aggregation."""
    __tablename__ = "fl_contributions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), nullable=False, index=True)
    exam_id = Column(String(36), nullable=False, index=True)
    
    # Which model this contribution is for ("audio_cnn" or "gaze_boundary")
    model_type = Column(String(50), nullable=False)
    
    # The actual payload (e.g. mean/var dict for audio confidence, or gaze boundaries)
    weight_delta = Column(JSON, nullable=False)
    sample_count = Column(Integer, default=0)
    
    # FL Aggregation tracking
    accepted = Column(Boolean, default=False)
    round_number = Column(Integer, default=0)
    contributed_at = Column(DateTime, default=datetime.utcnow)

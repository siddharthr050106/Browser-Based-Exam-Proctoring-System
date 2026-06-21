"""Federated Learning API Router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Dict, Any

from api.database import get_db
from api.models.fl_contribution import FLContribution
from api.config import settings

router = APIRouter(tags=["Federated Learning"])

class FLContributionRequest(BaseModel):
    session_id: str
    exam_id: str
    model_type: str
    weight_delta: Dict[str, Any]
    sample_count: int

@router.post("/contribute")
async def contribute(req: FLContributionRequest, db: AsyncSession = Depends(get_db)):
    """Receive a micro-payload FL update from a client session."""
    contrib = FLContribution(
        session_id=req.session_id,
        exam_id=req.exam_id,
        model_type=req.model_type,
        weight_delta=req.weight_delta,
        sample_count=req.sample_count,
    )
    db.add(contrib)
    await db.commit()
    
    return {"status": "success", "message": "FL contribution recorded"}

@router.get("/status")
async def get_fl_status(db: AsyncSession = Depends(get_db)):
    """Get high-level metrics about Federated Learning contributions."""
    result = await db.execute(select(func.count(FLContribution.id)))
    total_contributions = result.scalar() or 0
    
    result_accepted = await db.execute(
        select(func.count(FLContribution.id)).where(FLContribution.accepted == True)
    )
    accepted = result_accepted.scalar() or 0
    
    return {
        "status": "active",
        "total_contributions": total_contributions,
        "accepted_contributions": accepted,
        "min_sessions_needed": settings.FL_MIN_SESSIONS_BEFORE_UPDATE
    }

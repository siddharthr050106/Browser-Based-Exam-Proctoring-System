"""Federated Learning API Router.

Receives micro-payloads from sidecar (via frontend) at the end of each exam
session, stores them, and triggers FL aggregation rounds when enough
contributions accumulate.
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel

from api.database import get_db
from api.models.fl_contribution import FLContribution
from api.config import settings

logger = structlog.get_logger()
router = APIRouter(tags=["Federated Learning"])

# ── Global model version (in-memory, persisted to disk) ──
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "detection", "models")
FL_STATE_PATH = os.path.join(MODEL_DIR, "fl_state.json")


def _load_fl_state() -> dict:
    """Load FL round state from disk."""
    if os.path.exists(FL_STATE_PATH):
        with open(FL_STATE_PATH, "r") as f:
            return json.load(f)
    return {"current_round": 0, "last_aggregation": None, "total_contributions": 0}


def _save_fl_state(state: dict):
    """Persist FL round state to disk."""
    os.makedirs(os.path.dirname(FL_STATE_PATH), exist_ok=True)
    with open(FL_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ── Request / Response Schemas ──

class FLContributionRequest(BaseModel):
    """Matches the payload sent by ExamSession.jsx at end of exam."""
    session_id: str
    fl_boundary_params: Optional[List[Any]] = []
    fl_audio_params: Optional[Dict[str, Any]] = {}


class FLStatusResponse(BaseModel):
    status: str
    current_round: int
    total_contributions: int
    pending_contributions: int
    accepted_contributions: int
    min_sessions_needed: int
    last_aggregation: Optional[str] = None


class FLGlobalModelResponse(BaseModel):
    model_type: str
    round_number: int
    model_path: str
    available: bool


# ── Aggregation Logic ──

async def _maybe_trigger_aggregation(db: AsyncSession, model_type: str):
    """Check if we have enough pending contributions to run an FL round."""
    # Count un-aggregated contributions for this model type
    result = await db.execute(
        select(func.count(FLContribution.id)).where(
            and_(
                FLContribution.model_type == model_type,
                FLContribution.round_number == 0,  # Not yet aggregated
            )
        )
    )
    pending = result.scalar() or 0

    if pending < settings.FL_MIN_SESSIONS_BEFORE_UPDATE:
        logger.info("fl_not_enough_contributions",
                     model_type=model_type, pending=pending,
                     needed=settings.FL_MIN_SESSIONS_BEFORE_UPDATE)
        return

    logger.info("fl_triggering_aggregation",
                 model_type=model_type, contributions=pending)

    # Load FL state
    state = _load_fl_state()
    new_round = state["current_round"] + 1

    # Fetch all pending contributions
    rows = await db.execute(
        select(FLContribution).where(
            and_(
                FLContribution.model_type == model_type,
                FLContribution.round_number == 0,
            )
        )
    )
    contributions = rows.scalars().all()

    if model_type == "audio_cnn":
        _aggregate_audio(contributions, new_round)
    elif model_type == "gaze_boundary":
        _aggregate_gaze(contributions, new_round)

    # Mark contributions as aggregated
    for c in contributions:
        c.round_number = new_round
        c.accepted = True

    await db.commit()

    # Update FL state
    state["current_round"] = new_round
    state["last_aggregation"] = datetime.utcnow().isoformat()
    state["total_contributions"] = (state.get("total_contributions", 0)
                                    + len(contributions))
    _save_fl_state(state)

    logger.info("fl_round_complete", round=new_round,
                 model_type=model_type, contributions=len(contributions))


def _aggregate_audio(contributions: list, round_number: int):
    """Aggregate audio CNN calibration data using FedAvg-style averaging.

    Each contribution contains mean_probs and var_probs (4-class distributions).
    We compute a weighted average across all contributions to produce
    updated calibration thresholds.
    """
    all_means = []
    all_vars = []
    total_samples = 0

    for c in contributions:
        delta = c.weight_delta or {}
        if "mean_probs" in delta and "var_probs" in delta:
            n = delta.get("sample_count", 1)
            all_means.append((np.array(delta["mean_probs"]), n))
            all_vars.append((np.array(delta["var_probs"]), n))
            total_samples += n

    if not all_means or total_samples == 0:
        return

    # Weighted average of means
    weighted_mean = sum(m * n for m, n in all_means) / total_samples
    weighted_var = sum(v * n for v, n in all_vars) / total_samples

    # Add differential privacy noise
    noise_scale = settings.FL_NOISE_MULTIPLIER * np.std(weighted_mean)
    noisy_mean = weighted_mean + np.random.normal(0, max(noise_scale, 1e-6),
                                                   weighted_mean.shape)

    # Save aggregated calibration as JSON alongside the model
    calib_path = os.path.join(MODEL_DIR, "audio_calibration.json")
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(calib_path, "w") as f:
        json.dump({
            "round": round_number,
            "global_mean_probs": noisy_mean.tolist(),
            "global_var_probs": weighted_var.tolist(),
            "total_samples": total_samples,
            "num_contributors": len(all_means),
        }, f, indent=2)

    logger.info("fl_audio_calibration_updated",
                 round=round_number, samples=total_samples)


def _aggregate_gaze(contributions: list, round_number: int):
    """Aggregate gaze boundary parameters (yaw/pitch thresholds).

    Each contribution contains arrays of gaze yaw/pitch values from the session.
    We compute a global mean/std to calibrate the gaze anomaly thresholds.
    """
    all_yaws = []
    all_pitches = []

    for c in contributions:
        delta = c.weight_delta or {}
        if isinstance(delta, list):
            for entry in delta:
                if "mean_yaw" in entry:
                    all_yaws.append(entry["mean_yaw"])
                if "mean_pitch" in entry:
                    all_pitches.append(entry["mean_pitch"])

    if not all_yaws:
        return

    # Compute global gaze boundaries
    calib_path = os.path.join(MODEL_DIR, "gaze_calibration.json")
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(calib_path, "w") as f:
        json.dump({
            "round": round_number,
            "global_mean_yaw": float(np.mean(all_yaws)),
            "global_std_yaw": float(np.std(all_yaws)),
            "global_mean_pitch": float(np.mean(all_pitches)),
            "global_std_pitch": float(np.std(all_pitches)),
            "num_contributors": len(all_yaws),
        }, f, indent=2)

    logger.info("fl_gaze_calibration_updated",
                 round=round_number, contributors=len(all_yaws))


# ── Endpoints ──

@router.post("/contribute")
async def contribute(
    req: FLContributionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Receive micro-payloads from the frontend at the end of an exam session.

    The frontend sends both gaze boundary params and audio calibration params
    collected by the local sidecar. We store them separately and check if
    an FL aggregation round should be triggered.
    """
    created = []

    # Store gaze boundary contributions
    if req.fl_boundary_params:
        gaze_contrib = FLContribution(
            session_id=req.session_id,
            exam_id=req.session_id,  # Use session_id as fallback
            model_type="gaze_boundary",
            weight_delta=req.fl_boundary_params if isinstance(req.fl_boundary_params, dict) else {"data": req.fl_boundary_params},
            sample_count=1,
        )
        db.add(gaze_contrib)
        created.append("gaze_boundary")

    # Store audio CNN calibration contributions
    if req.fl_audio_params and isinstance(req.fl_audio_params, dict) and len(req.fl_audio_params) > 0:
        audio_contrib = FLContribution(
            session_id=req.session_id,
            exam_id=req.session_id,
            model_type="audio_cnn",
            weight_delta=req.fl_audio_params,
            sample_count=req.fl_audio_params.get("sample_count", 1),
        )
        db.add(audio_contrib)
        created.append("audio_cnn")

    if created:
        await db.commit()
        logger.info("fl_contribution_stored",
                     session_id=req.session_id, types=created)

        # Check if we should trigger aggregation (async, non-blocking)
        for model_type in created:
            await _maybe_trigger_aggregation(db, model_type)

    return {
        "status": "success",
        "contributions_stored": created,
        "message": f"Stored {len(created)} FL contribution(s)",
    }


@router.get("/status", response_model=FLStatusResponse)
async def get_fl_status(db: AsyncSession = Depends(get_db)):
    """Get high-level metrics about Federated Learning state."""
    state = _load_fl_state()

    result_total = await db.execute(select(func.count(FLContribution.id)))
    total = result_total.scalar() or 0

    result_pending = await db.execute(
        select(func.count(FLContribution.id)).where(
            FLContribution.round_number == 0
        )
    )
    pending = result_pending.scalar() or 0

    result_accepted = await db.execute(
        select(func.count(FLContribution.id)).where(
            FLContribution.accepted == True
        )
    )
    accepted = result_accepted.scalar() or 0

    return FLStatusResponse(
        status="active",
        current_round=state["current_round"],
        total_contributions=total,
        pending_contributions=pending,
        accepted_contributions=accepted,
        min_sessions_needed=settings.FL_MIN_SESSIONS_BEFORE_UPDATE,
        last_aggregation=state.get("last_aggregation"),
    )


@router.get("/global-model/{model_type}")
async def get_global_model(model_type: str):
    """Return info about the current global model for a given type.

    Clients can use this to check if a newer model is available.
    """
    state = _load_fl_state()

    if model_type == "audio_cnn":
        model_path = os.path.join(MODEL_DIR, "audio_cnn.onnx")
        calib_path = os.path.join(MODEL_DIR, "audio_calibration.json")
        calibration = None
        if os.path.exists(calib_path):
            with open(calib_path, "r") as f:
                calibration = json.load(f)

        return {
            "model_type": "audio_cnn",
            "round_number": state["current_round"],
            "model_available": os.path.exists(model_path),
            "calibration": calibration,
        }

    elif model_type == "gaze_boundary":
        calib_path = os.path.join(MODEL_DIR, "gaze_calibration.json")
        calibration = None
        if os.path.exists(calib_path):
            with open(calib_path, "r") as f:
                calibration = json.load(f)

        return {
            "model_type": "gaze_boundary",
            "round_number": state["current_round"],
            "model_available": True,  # Gaze uses calibration params, not a model file
            "calibration": calibration,
        }

    return {
        "model_type": model_type,
        "round_number": 0,
        "model_available": False,
        "calibration": None,
    }

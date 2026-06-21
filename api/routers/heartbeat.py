"""Heartbeat API — receives telemetry from Electron desktop clients.

This router handles:
- Periodic heartbeat packets (gear, trust score, session liveness)
- Batched event ingestion (Gear 2 bundled INFO events)
- Emergency beacon (Gear 4 CRITICAL via navigator.sendBeacon)
- Network probe (RTT/bandwidth measurement endpoint)
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.session import ExamSession, NetworkTier
from api.models.event import DetectionEvent, EventType, EventTier

logger = structlog.get_logger()

router = APIRouter(prefix="/api/heartbeat", tags=["heartbeat"])


# ── Request Models ──

class HeartbeatRequest(BaseModel):
    sid: str  # session UUID
    ts: int   # client timestamp (ms)
    gear: int  # 1-4
    trust: float  # 0.0 - 1.0
    bundled_info: Optional[list[dict[str, Any]]] = None


class BatchEventsRequest(BaseModel):
    sid: str
    events: list[dict[str, Any]]


# ── Heartbeat Endpoint ──

@router.post("")
async def receive_heartbeat(req: HeartbeatRequest, db: AsyncSession = Depends(get_db)):
    """Receive a heartbeat from the Electron desktop client.

    Updates session liveness, gear, and trust score.
    Optionally processes bundled INFO events (Gear 2).
    """
    try:
        session_id = uuid.UUID(req.sid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    # Map gear number to NetworkTier enum
    gear_to_tier = {
        1: NetworkTier.TIER_1,
        2: NetworkTier.TIER_2,
        3: NetworkTier.TIER_3,
        4: NetworkTier.TIER_4,
    }
    tier = gear_to_tier.get(req.gear, NetworkTier.TIER_1)

    # Update session
    now = datetime.now(timezone.utc)
    stmt = (
        update(ExamSession)
        .where(ExamSession.id == session_id)
        .values(
            network_tier=tier,
            trust_score=max(0.0, min(1.0, req.trust)),
            current_gear=req.gear,
            last_heartbeat_at=now,
        )
    )
    await db.execute(stmt)

    # Track Gear 4 start time
    if req.gear == 4:
        # Set gear_4_start if not already set
        result = await db.execute(
            select(ExamSession.gear_4_start).where(ExamSession.id == session_id)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            await db.execute(
                update(ExamSession)
                .where(ExamSession.id == session_id)
                .values(gear_4_start=now)
            )
    else:
        # Clear Gear 4 timer when leaving Gear 4
        await db.execute(
            update(ExamSession)
            .where(ExamSession.id == session_id)
            .values(gear_4_start=None)
        )

    # Process bundled INFO events if present (Gear 2)
    inserted = 0
    if req.bundled_info:
        for evt in req.bundled_info:
            try:
                event = DetectionEvent(
                    session_id=session_id,
                    event_type=evt.get("event_type", "unknown"),
                    tier=evt.get("tier", "info"),
                    confidence=evt.get("confidence"),
                    metadata_json=evt.get("metadata"),
                )
                db.add(event)
                inserted += 1
            except Exception as e:
                logger.warning("bundled_event_insert_failed", error=str(e))

    await db.commit()

    logger.debug(
        "heartbeat_received",
        session_id=str(session_id),
        gear=req.gear,
        trust=req.trust,
        bundled=inserted,
    )

    return {"status": "ok", "bundled_inserted": inserted}


# ── Batch Events Endpoint (flush from IndexedDB or Gear 2 bundle) ──

@router.post("/events")
async def receive_batch_events(req: BatchEventsRequest, db: AsyncSession = Depends(get_db)):
    """Receive a batch of events from the client.

    Used for:
    - Gear 2 bundled INFO events
    - IndexedDB offline buffer flush (Gear 4 recovery)
    """
    try:
        session_id = uuid.UUID(req.sid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    inserted = 0
    for evt in req.events:
        try:
            event = DetectionEvent(
                session_id=session_id,
                event_type=evt.get("event_type", "unknown"),
                tier=evt.get("tier", "info"),
                confidence=evt.get("confidence"),
                metadata_json=evt.get("metadata"),
            )
            db.add(event)
            inserted += 1
        except Exception as e:
            logger.warning("batch_event_insert_failed", error=str(e))

    await db.commit()

    # Broadcast events to proctor WebSocket
    try:
        from api.routers.ws import broadcast_event
        for evt in req.events:
            await broadcast_event(
                str(session_id),
                {
                    "type": "detection_event",
                    "data": {
                        "event_type": evt.get("event_type"),
                        "tier": evt.get("tier"),
                        "confidence": evt.get("confidence"),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
    except Exception as e:
        logger.debug("broadcast_failed", error=str(e))

    logger.info("batch_events_received", session_id=str(session_id), count=inserted)
    return {"status": "ok", "accepted": inserted}


# ── Emergency Beacon (Gear 4 CRITICAL via navigator.sendBeacon) ──

@router.post("/emergency")
async def receive_emergency(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive a CRITICAL emergency event via navigator.sendBeacon.

    sendBeacon may send as text/plain or application/json.
    We handle both.
    """
    try:
        body = await request.json()
    except Exception:
        # Try to parse as text
        raw = await request.body()
        try:
            import json
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid beacon payload")

    sid = body.get("sid")
    if not sid:
        raise HTTPException(status_code=400, detail="Missing session ID")

    try:
        session_id = uuid.UUID(sid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID")

    event = DetectionEvent(
        session_id=session_id,
        event_type=body.get("type", "emergency"),
        tier="critical",
        confidence=1.0,
        metadata_json={"source": "beacon", "client_ts": body.get("ts")},
    )
    db.add(event)
    await db.commit()

    # Broadcast to proctor
    try:
        from api.routers.ws import broadcast_event
        await broadcast_event(
            str(session_id),
            {
                "type": "detection_event",
                "data": {
                    "event_type": body.get("type", "emergency"),
                    "tier": "critical",
                    "confidence": 1.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "emergency_beacon",
                },
            },
        )
    except Exception:
        pass

    logger.warning("emergency_beacon_received", session_id=str(session_id), type=body.get("type"))
    return {"status": "ok"}


# ── Network Probe (for RTT / bandwidth measurement) ──

@router.get("/probe")
async def network_probe():
    """Return a ~100KB payload for RTT and bandwidth measurement.

    The client measures time from request to response to determine
    network quality and gear classification.
    """
    # Generate a deterministic 100KB payload (no crypto overhead)
    probe_size = 100 * 1024  # 100 KB
    payload = b"X" * probe_size

    return {
        "server_ts": int(time.time() * 1000),
        "probe_size": probe_size,
        "data": payload.decode("ascii"),
    }

"""Detection Worker — standalone service that processes video frames.

This runs as a SEPARATE PROCESS from the API server.
It receives frames via a REST endpoint, runs the detection pipeline,
and publishes results to Redis. The API process subscribes to Redis
and persists events to PostgreSQL + broadcasts via WebSocket.

Architecture:
  Client Browser ──(POST /frames)──▶  Detection Worker
                                           │
                                      Detection Pipeline
                                      (Face, YOLO, BG, Gaze, Anomaly)
                                           │
                                      Redis PUBLISH
                                           │
                                      API Subscriber ──▶ DB + WS
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from io import BytesIO

import cv2
import numpy as np
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.config import settings
from api.services.redis_bridge import RedisEventPublisher
from detection.detection_pipeline import DetectionPipeline

logger = structlog.get_logger()

app = FastAPI(title="BEZP Detection Worker", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Global state
_publisher: RedisEventPublisher | None = None
_pipelines: dict[str, DetectionPipeline] = {}  # session_id → pipeline


@app.on_event("startup")
async def startup():
    global _publisher
    _publisher = RedisEventPublisher(settings.REDIS_URL)
    await _publisher.connect()
    logger.info("detection_worker_started")


@app.on_event("shutdown")
async def shutdown():
    if _publisher:
        await _publisher.close()
    for pipeline in _pipelines.values():
        pipeline.close()
    logger.info("detection_worker_shutdown")


class FrameRequest(BaseModel):
    session_id: str
    frame_base64: str  # base64-encoded JPEG frame
    is_first_frame: bool = False


class BrowserEventRequest(BaseModel):
    session_id: str
    event_type: str  # tab_switch, window_blur, fullscreen_exit


@app.post("/detect/frame")
async def process_frame(req: FrameRequest):
    """Process a single video frame through the detection pipeline.

    Called by the client-side JavaScript at the configured FPS rate.
    The frame is processed locally (detection runs here), and only
    detection metadata is published to Redis.
    """
    # Decode frame
    try:
        frame_bytes = base64.b64decode(req.frame_base64)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Failed to decode frame")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame: {e}")

    # Get or create pipeline for this session
    if req.session_id not in _pipelines:
        _pipelines[req.session_id] = DetectionPipeline({
            "yolo_confidence": settings.YOLO_CONFIDENCE_THRESHOLD,
            "phone_consecutive": settings.PHONE_CONSECUTIVE_FRAMES,
            "person_consecutive": settings.PERSON_CONSECUTIVE_FRAMES,
            "no_face_timeout": settings.NO_FACE_TIMEOUT_SECONDS,
            "ssim_threshold": settings.BACKGROUND_SSIM_THRESHOLD,
            "bg_interval_min": settings.BACKGROUND_CHECK_INTERVAL_MINUTES,
            "identity_threshold": settings.IDENTITY_COSINE_THRESHOLD,
            "yaw_threshold": settings.GAZE_YAW_THRESHOLD,
            "pitch_threshold": settings.GAZE_PITCH_THRESHOLD,
            "anomaly_duration": settings.GAZE_ANOMALY_DURATION_SECONDS,
            "tab_switch_count": settings.TAB_SWITCH_FLAG_COUNT,
            "tab_switch_window": settings.TAB_SWITCH_FLAG_WINDOW_MINUTES * 60,
        })

    pipeline = _pipelines[req.session_id]

    # Initialize on first frame
    if req.is_first_frame:
        pipeline.start_session(frame)
        return {"status": "session_initialized", "signals": []}

    # Run detection pipeline
    signals = pipeline.process_frame(frame)

    # Publish each signal to Redis
    published = []
    for signal in signals:
        await _publisher.publish_event(
            session_id=req.session_id,
            event_type=signal.event_type,
            tier=signal.tier.value,
            confidence=signal.confidence,
            metadata=signal.metadata,
        )
        published.append({
            "event_type": signal.event_type,
            "tier": signal.tier.value,
            "requires_clip": signal.requires_clip,
        })

    # Publish gaze snapshot from the pipeline's last result (avoids duplicate face_gate call)
    if hasattr(pipeline, '_last_gaze') and pipeline._last_gaze is not None:
        gz = pipeline._last_gaze
        await _publisher.publish_gaze(
            session_id=req.session_id,
            head_yaw=gz.get("yaw", 0.0),
            head_pitch=gz.get("pitch", 0.0),
            anomaly_score=gz.get("anomaly_score", 0.0),
        )

    return {"status": "processed", "signals": published}


@app.post("/detect/browser-event")
async def process_browser_event(req: BrowserEventRequest):
    """Process a browser-level event (tab switch, blur, fullscreen exit).

    These events come from the client JavaScript and don't need
    the detection pipeline — they go straight through the rule engine.
    """
    if req.session_id not in _pipelines:
        _pipelines[req.session_id] = DetectionPipeline()

    signal = _pipelines[req.session_id].process_browser_event(req.event_type)

    await _publisher.publish_event(
        session_id=req.session_id,
        event_type=signal.event_type,
        tier=signal.tier.value,
        confidence=signal.confidence,
        metadata=signal.metadata,
    )

    return {
        "status": "processed",
        "event_type": signal.event_type,
        "tier": signal.tier.value,
        "requires_clip": signal.requires_clip,
    }


@app.post("/detect/end-session/{session_id}")
async def end_session(session_id: str):
    """Clean up detection pipeline for an ended session."""
    if session_id in _pipelines:
        # Export FL boundary params before cleanup
        boundary = _pipelines[session_id].anomaly.get_boundary_params()
        _pipelines[session_id].close()
        del _pipelines[session_id]
        logger.info("detection_session_ended", session_id=session_id)
        return {"status": "session_ended", "fl_boundary_params": boundary}
    return {"status": "session_not_found"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "bezp-detection-worker",
        "active_sessions": len(_pipelines),
    }

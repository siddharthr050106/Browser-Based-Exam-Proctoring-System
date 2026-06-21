"""BEZP Python Sidecar — Local detection service.

Runs on 127.0.0.1:8765 (localhost ONLY — never exposed to the network).
Wraps the EXISTING detection pipeline unchanged: FaceGate, YOLO, Background,
Gaze, Anomaly, and RuleEngine all run exactly as they did in the server-side
detection worker.

The Electron renderer sends frames here over localhost IPC. Detection results
are returned directly in the HTTP response. No frames ever leave the device.

Architecture:
  Electron Renderer ──(localhost POST)──▶  Sidecar (this)
                                               │
                                          Detection Pipeline
                                          (Face, YOLO, BG, Gaze, Anomaly)
                                               │
                                          Returns JSON signals
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import uuid
from io import BytesIO

import cv2
import numpy as np
import structlog
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to path so we can import detection and api.config
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from detection.detection_pipeline import DetectionPipeline

logger = structlog.get_logger()

SIDECAR_PORT = int(os.environ.get("SIDECAR_PORT", "8765"))

app = FastAPI(
    title="BEZP Sidecar — Local Detection",
    description="Runs on localhost only. Never exposed to the network.",
    version="1.0.0",
)

# Allow requests from Electron renderer (file:// and localhost origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global State ──
_pipelines: dict[str, DetectionPipeline] = {}  # session_id → pipeline


def _get_pipeline_config() -> dict:
    """Load detection config. Uses defaults if api.config is not available."""
    try:
        from api.config import settings
        return {
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
        }
    except ImportError:
        logger.warning("api.config not available, using detection defaults")
        return {}


# ── Request Models ──

class FrameRequest(BaseModel):
    session_id: str
    frame_base64: str  # base64-encoded JPEG frame
    is_first_frame: bool = False


class BrowserEventRequest(BaseModel):
    session_id: str
    event_type: str  # tab_switch, window_blur, fullscreen_exit


# ── Detection Endpoints (same interface as the old worker.py) ──

@app.post("/detect/frame")
async def process_frame(req: FrameRequest):
    """Process a single video frame through the full detection pipeline.

    Called by the Electron renderer at gear-controlled FPS.
    The frame NEVER leaves this machine — localhost only.
    Returns detection signals directly in the response.
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
        _pipelines[req.session_id] = DetectionPipeline(_get_pipeline_config())

    pipeline = _pipelines[req.session_id]

    # Initialize on first frame
    if req.is_first_frame:
        pipeline.start_session(frame)
        return {"status": "session_initialized", "signals": []}

    # Run detection pipeline (ALL existing rule-based detections intact)
    signals = pipeline.process_frame(frame)

    # Build response
    published = []
    for signal in signals:
        published.append({
            "event_type": signal.event_type,
            "tier": signal.tier.value,
            "confidence": signal.confidence,
            "metadata": signal.metadata,
            "requires_clip": signal.requires_clip,
        })

    # Include gaze data if available (for trust score / timeline)
    gaze_data = None
    if hasattr(pipeline, '_last_gaze') and pipeline._last_gaze is not None:
        gaze_data = pipeline._last_gaze

    return {
        "status": "processed",
        "signals": published,
        "gaze": gaze_data,
    }


@app.post("/detect/browser-event")
async def process_browser_event(req: BrowserEventRequest):
    """Process a browser-level event (tab switch, blur, fullscreen exit).

    These go straight through the rule engine — no frame processing needed.
    """
    if req.session_id not in _pipelines:
        _pipelines[req.session_id] = DetectionPipeline(_get_pipeline_config())

    signal = _pipelines[req.session_id].process_browser_event(req.event_type)

    return {
        "status": "processed",
        "event_type": signal.event_type,
        "tier": signal.tier.value,
        "confidence": signal.confidence,
        "metadata": signal.metadata,
        "requires_clip": signal.requires_clip,
    }


@app.post("/detect/end-session/{session_id}")
async def end_session(session_id: str):
    """Clean up detection pipeline for an ended session.

    Returns FL boundary params (mean/var of gaze calibration data)
    for later submission to the FL server.
    """
    if session_id in _pipelines:
        boundary = _pipelines[session_id].anomaly.get_boundary_params()
        audio_boundary = _pipelines[session_id].audio.get_boundary_params()
        _pipelines[session_id].close()
        del _pipelines[session_id]
        logger.info("sidecar_session_ended", session_id=session_id)
        return {
            "status": "session_ended", 
            "fl_boundary_params": boundary,
            "fl_audio_params": audio_boundary
        }
    return {"status": "session_not_found"}


# ── Audio Detection (Phase 2 — CNN) ──

@app.websocket("/ws/audio/{session_id}")
async def audio_websocket(websocket: WebSocket, session_id: str):
    """Receive audio chunks from the Electron renderer for analysis.

    Uses the PyTorch Audio CNN (via ONNX) to classify 3-second chunks
    into silence, single_speaker, multi_speaker, or background_noise.
    
    Audio arrives as base64-encoded 16kHz PCM int16 chunks.
    """
    await websocket.accept()
    logger.info("audio_ws_connected", session_id=session_id)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                # Decode base64 PCM audio
                audio_bytes = base64.b64decode(data)
                samples = np.frombuffer(audio_bytes, dtype=np.int16)

                # Initialize pipeline if not exists
                if session_id not in _pipelines:
                    _pipelines[session_id] = DetectionPipeline(_get_pipeline_config())

                signals, ar = _pipelines[session_id].process_audio(samples)

                # Convert signals to response format
                flag = None
                if signals:
                    # Take the highest tier signal for the immediate response
                    tier_val = {"info": 1, "warning": 2, "flag": 3, "critical": 4}
                    sig = max(signals, key=lambda s: tier_val.get(s.tier.value, 0))
                    flag = {
                        "event_type": sig.event_type,
                        "tier": sig.tier.value,
                        "confidence": sig.confidence,
                        "metadata": sig.metadata,
                        "requires_clip": getattr(sig, "requires_clip", False)
                    }

                await websocket.send_json({
                    "class": ar.predicted_class,
                    "confidence": ar.confidence,
                    "is_speech": ar.is_speech,
                    "flag": flag,
                })

            except Exception as e:
                logger.error("audio_process_error", error=str(e))

    except WebSocketDisconnect:
        logger.info("audio_ws_disconnected", session_id=session_id)


# ── Health ──

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "bezp-sidecar",
        "host": "127.0.0.1",
        "port": SIDECAR_PORT,
        "active_sessions": len(_pipelines),
    }


# ── Entry Point ──

if __name__ == "__main__":
    import uvicorn

    logger.info(
        "sidecar_starting",
        host="127.0.0.1",
        port=SIDECAR_PORT,
        msg="Bound to localhost ONLY — no network exposure",
    )
    uvicorn.run(
        app,
        host="127.0.0.1",  # CRITICAL: localhost only, never 0.0.0.0
        port=SIDECAR_PORT,
        log_level="info",
    )

"""WebSocket router — real-time event metadata streaming to proctors.

PRIVACY: Only structured event JSON (flags, scores, timestamps) is sent.
NO video data is ever transmitted over WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Dict, Set

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])

# Connected proctor clients, keyed by session_id they're monitoring
_proctor_connections: Dict[str, Set[WebSocket]] = {}


async def broadcast_event(session_id: uuid.UUID, event_data: dict) -> None:
    """Broadcast a detection event to all proctors monitoring this session.

    Called by the events router when a new event is created.
    Only sends structured JSON metadata — never video.
    """
    key = str(session_id)
    if key not in _proctor_connections:
        return

    dead_connections = set()
    message = json.dumps({
        "type": "detection_event",
        "session_id": key,
        "data": event_data,
    })

    for ws in _proctor_connections[key]:
        try:
            await ws.send_text(message)
        except Exception:
            dead_connections.add(ws)

    # Clean up dead connections
    _proctor_connections[key] -= dead_connections
    if not _proctor_connections[key]:
        del _proctor_connections[key]


@router.websocket("/ws/proctor/{session_id}")
async def proctor_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for proctors to receive real-time event metadata.

    Proctors connect to monitor a specific exam session.
    They receive structured JSON events — NO video data.

    Message format sent to proctor:
    {
        "type": "detection_event",
        "session_id": "uuid",
        "data": {
            "event_type": "phone_detected",
            "tier": "flag",
            "confidence": 0.85,
            "timestamp": "2026-01-01T00:00:00Z",
            "metadata_json": {...}
        }
    }
    """
    await websocket.accept()

    # Register connection
    if session_id not in _proctor_connections:
        _proctor_connections[session_id] = set()
    _proctor_connections[session_id].add(websocket)

    logger.info("proctor_connected", session_id=session_id)

    try:
        while True:
            # Keep connection alive, receive any proctor commands
            data = await websocket.receive_text()
            # Handle proctor commands (e.g., pause session)
            try:
                command = json.loads(data)
                if command.get("action") == "pause_session":
                    logger.info("proctor_pause_requested", session_id=session_id)
                    # TODO: Wire to session service
                elif command.get("action") == "resume_session":
                    logger.info("proctor_resume_requested", session_id=session_id)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        logger.info("proctor_disconnected", session_id=session_id)
    finally:
        if session_id in _proctor_connections:
            _proctor_connections[session_id].discard(websocket)
            if not _proctor_connections[session_id]:
                del _proctor_connections[session_id]

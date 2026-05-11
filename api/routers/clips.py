"""Clips router — 30-second video clip upload and retrieval.

Supports two storage backends:
1. Local filesystem (default, no external dependencies)
2. MinIO/S3 (for production with object storage)

Warning clips are always stored locally for reliability.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.services import event_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/clips", tags=["clips"])

# Local clip storage directory
CLIPS_DIR = Path(__file__).resolve().parent.parent.parent / "clip_storage"
CLIPS_DIR.mkdir(exist_ok=True)


# ── Warning Clip (local storage — always works) ──

@router.post("/warning/{session_id}", status_code=status.HTTP_201_CREATED)
async def upload_warning_clip(
    session_id: str,
    clip: UploadFile = File(...),
):
    """Upload a 30-second warning clip (20s pre + 10s post warning).

    Stored locally — no S3/MinIO required.
    """
    session_dir = CLIPS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    filename = f"warning_{uuid.uuid4().hex[:8]}.webm"
    filepath = session_dir / filename
    content = await clip.read()

    with open(filepath, "wb") as f:
        f.write(content)

    clip_url = f"/api/clips/files/{session_id}/{filename}"

    logger.info("warning_clip_uploaded",
                session_id=session_id,
                size_bytes=len(content),
                path=str(filepath))

    # Broadcast clip availability to proctors
    from api.routers.ws import broadcast_event
    await broadcast_event(uuid.UUID(session_id), {
        "event_type": "warning_clip_ready",
        "tier": "info",
        "clip_url": clip_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"clip_url": clip_url, "status": "uploaded", "size_bytes": len(content)}


@router.get("/files/{session_id}/{filename}")
async def serve_clip(session_id: str, filename: str):
    """Serve a locally stored clip file."""
    filepath = CLIPS_DIR / session_id / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Clip file not found")

    # Security: prevent path traversal
    try:
        filepath.resolve().relative_to(CLIPS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(path=str(filepath), media_type="video/webm", filename=filename)


@router.get("/warning/{session_id}")
async def get_warning_clip(session_id: str):
    """Get the latest warning clip URL for a session."""
    session_dir = CLIPS_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="No clips for this session")

    clips = sorted(session_dir.glob("warning_*.webm"), key=os.path.getmtime, reverse=True)
    if not clips:
        raise HTTPException(status_code=404, detail="No warning clip available yet")

    latest = clips[0]
    return {"clip_url": f"/api/clips/files/{session_id}/{latest.name}", "session_id": session_id}


# ── Event Clips (MinIO with local fallback) ──

@router.post("/{session_id}/{event_id}", status_code=status.HTTP_201_CREATED)
async def upload_clip(
    session_id: uuid.UUID,
    event_id: uuid.UUID,
    clip: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a 30-second video clip for a flagged event."""
    content = await clip.read()

    # Try MinIO, fall back to local
    try:
        s3 = _get_s3_client()
        object_key = f"clips/{session_id}/{event_id}/{clip.filename}"
        try:
            s3.head_bucket(Bucket=settings.MINIO_BUCKET)
        except Exception:
            s3.create_bucket(Bucket=settings.MINIO_BUCKET)
        s3.put_object(Bucket=settings.MINIO_BUCKET, Key=object_key, Body=content,
                      ContentType=clip.content_type or "video/webm")
        clip_url = f"http://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{object_key}"
    except Exception:
        session_dir = CLIPS_DIR / str(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        filename = f"event_{event_id}.webm"
        with open(session_dir / filename, "wb") as f:
            f.write(content)
        clip_url = f"/api/clips/files/{session_id}/{filename}"

    try:
        await event_service.set_clip_url(db, event_id, clip_url)
    except Exception:
        pass

    logger.info("clip_uploaded", session_id=str(session_id), event_id=str(event_id))
    return {"clip_url": clip_url, "status": "uploaded"}


@router.get("/{event_id}")
async def get_clip(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve the clip URL for a flagged event."""
    from sqlalchemy import select
    from api.models.event import DetectionEvent

    result = await db.execute(select(DetectionEvent).where(DetectionEvent.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.clip_url is None:
        raise HTTPException(status_code=404, detail="No clip available for this event")
    return {"event_id": str(event_id), "clip_url": event.clip_url}


def _get_s3_client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.MINIO_USE_SSL else ''}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )

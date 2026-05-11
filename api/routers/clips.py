"""Clips router — 30-second video clip upload and retrieval.

Video clips are uploaded ONLY when a FLAG/CRITICAL event is triggered.
No live video is ever streamed. This is the privacy-first design.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.database import get_db
from api.services import event_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/clips", tags=["clips"])


def _get_s3_client():
    """Get a boto3 S3 client configured for MinIO."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"http{'s' if settings.MINIO_USE_SSL else ''}://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
    )


@router.post("/{session_id}/{event_id}", status_code=status.HTTP_201_CREATED)
async def upload_clip(
    session_id: uuid.UUID,
    event_id: uuid.UUID,
    clip: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a 30-second video clip for a flagged event.

    This endpoint is called ONLY when a FLAG or CRITICAL event triggers
    the client-side 30-second buffer to freeze and upload.
    """
    object_key = f"clips/{session_id}/{event_id}/{clip.filename}"

    try:
        s3 = _get_s3_client()

        # Ensure bucket exists
        try:
            s3.head_bucket(Bucket=settings.MINIO_BUCKET)
        except Exception:
            s3.create_bucket(Bucket=settings.MINIO_BUCKET)

        # Upload clip
        content = await clip.read()
        s3.put_object(
            Bucket=settings.MINIO_BUCKET,
            Key=object_key,
            Body=content,
            ContentType=clip.content_type or "video/webm",
        )

        clip_url = f"http://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{object_key}"

        # Attach clip URL to the event record
        await event_service.set_clip_url(db, event_id, clip_url)

        logger.info("clip_uploaded", session_id=str(session_id), event_id=str(event_id))
        return {"clip_url": clip_url, "status": "uploaded"}

    except Exception as e:
        logger.error("clip_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Clip upload failed: {str(e)}")


@router.get("/{event_id}")
async def get_clip(event_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve the clip URL for a flagged event."""
    from sqlalchemy import select
    from api.models.event import DetectionEvent

    result = await db.execute(
        select(DetectionEvent).where(DetectionEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.clip_url is None:
        raise HTTPException(status_code=404, detail="No clip available for this event")
    return {"event_id": str(event_id), "clip_url": event.clip_url}

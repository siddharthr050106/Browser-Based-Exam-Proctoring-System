"""Redis Event Bridge — connects detection pipeline to the API layer.

Architecture:
  Detection Worker  ──(Redis PUBLISH)──▶  API Subscriber  ──▶  DB Write + WebSocket Broadcast

The detection worker publishes detection signals as JSON to a Redis channel.
The API subscriber listens, writes events to PostgreSQL, and broadcasts
to connected proctor WebSockets. This decouples detection from the API process.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()

CHANNEL_EVENTS = "bezp:detection_events"
CHANNEL_GAZE = "bezp:gaze_snapshots"


class RedisEventPublisher:
    """Used by the detection worker to publish events to Redis."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def connect(self):
        self._redis = aioredis.from_url(self._redis_url)
        logger.info("redis_publisher_connected")

    async def publish_event(self, session_id: str, event_type: str, tier: str,
                            confidence: float = None, metadata: dict = None):
        """Publish a detection event to Redis."""
        payload = {
            "session_id": session_id,
            "event_type": event_type,
            "tier": tier,
            "confidence": confidence,
            "metadata_json": metadata,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._redis.publish(CHANNEL_EVENTS, json.dumps(payload))

    async def publish_gaze(self, session_id: str, gaze_x: float = None,
                           gaze_y: float = None, head_yaw: float = None,
                           head_pitch: float = None, anomaly_score: float = None):
        """Publish a gaze snapshot to Redis."""
        payload = {
            "session_id": session_id,
            "gaze_x": gaze_x,
            "gaze_y": gaze_y,
            "head_yaw": head_yaw,
            "head_pitch": head_pitch,
            "anomaly_score": anomaly_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._redis.publish(CHANNEL_GAZE, json.dumps(payload))

    async def close(self):
        if self._redis:
            await self._redis.close()


class RedisEventSubscriber:
    """Used by the API process to subscribe to detection events from Redis.

    On each event: writes to PostgreSQL and broadcasts via WebSocket.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def start(self, db_session_factory, ws_broadcast_fn):
        """Start listening for detection events.

        Args:
            db_session_factory: Async session factory for DB writes.
            ws_broadcast_fn: Coroutine to broadcast events via WebSocket.
        """
        self._redis = aioredis.from_url(self._redis_url)
        self._running = True
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL_EVENTS, CHANNEL_GAZE)
        logger.info("redis_subscriber_started")

        try:
            while self._running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                data = json.loads(message["data"])

                if channel == CHANNEL_EVENTS:
                    await self._handle_event(data, db_session_factory, ws_broadcast_fn)
                elif channel == CHANNEL_GAZE:
                    await self._handle_gaze(data, db_session_factory)

        except asyncio.CancelledError:
            logger.info("redis_subscriber_cancelled")
        finally:
            await pubsub.unsubscribe()
            await self._redis.close()

    async def _handle_event(self, data: dict, db_session_factory, ws_broadcast_fn):
        """Write detection event to DB and broadcast to proctors."""
        from api.models.event import DetectionEvent, EventType, EventTier

        try:
            async with db_session_factory() as db:
                event = DetectionEvent(
                    session_id=uuid.UUID(data["session_id"]),
                    event_type=EventType(data["event_type"]),
                    tier=EventTier(data["tier"]),
                    confidence=data.get("confidence"),
                    metadata_json=data.get("metadata_json"),
                )
                db.add(event)
                await db.commit()
                await db.refresh(event)

                # Broadcast to proctor WebSocket
                await ws_broadcast_fn(
                    uuid.UUID(data["session_id"]),
                    {
                        "id": str(event.id),
                        "event_type": data["event_type"],
                        "tier": data["tier"],
                        "confidence": data.get("confidence"),
                        "timestamp": data.get("timestamp"),
                        "metadata_json": data.get("metadata_json"),
                    }
                )
                logger.info("event_persisted", event_type=data["event_type"], tier=data["tier"])

        except Exception as e:
            logger.error("event_persist_failed", error=str(e))

    async def _handle_gaze(self, data: dict, db_session_factory):
        """Write gaze snapshot to DB."""
        from api.models.gaze_snapshot import GazeSnapshot

        try:
            async with db_session_factory() as db:
                snapshot = GazeSnapshot(
                    session_id=uuid.UUID(data["session_id"]),
                    gaze_x=data.get("gaze_x"),
                    gaze_y=data.get("gaze_y"),
                    head_yaw=data.get("head_yaw"),
                    head_pitch=data.get("head_pitch"),
                    anomaly_score=data.get("anomaly_score"),
                )
                db.add(snapshot)
                await db.commit()
        except Exception as e:
            logger.error("gaze_persist_failed", error=str(e))

    async def stop(self):
        self._running = False

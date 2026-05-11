"""Tests for the Redis event bridge."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.redis_bridge import RedisEventPublisher, RedisEventSubscriber, CHANNEL_EVENTS, CHANNEL_GAZE


@pytest.mark.asyncio
async def test_publisher_connect():
    """Publisher should connect to Redis."""
    pub = RedisEventPublisher("redis://localhost:6379/0")
    with patch("redis.asyncio.from_url") as mock_from_url:
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis
        await pub.connect()
        assert pub._redis is not None


@pytest.mark.asyncio
async def test_publisher_publish_event():
    """Publisher should publish JSON to the events channel."""
    pub = RedisEventPublisher()
    pub._redis = AsyncMock()

    await pub.publish_event(
        session_id="test-session-123",
        event_type="phone_detected",
        tier="flag",
        confidence=0.85,
        metadata={"phone_bbox": [100, 200, 300, 400]},
    )

    pub._redis.publish.assert_called_once()
    call_args = pub._redis.publish.call_args
    assert call_args[0][0] == CHANNEL_EVENTS
    payload = json.loads(call_args[0][1])
    assert payload["event_type"] == "phone_detected"
    assert payload["tier"] == "flag"
    assert payload["confidence"] == 0.85


@pytest.mark.asyncio
async def test_publisher_publish_gaze():
    """Publisher should publish gaze snapshot to Redis."""
    pub = RedisEventPublisher()
    pub._redis = AsyncMock()

    await pub.publish_gaze(
        session_id="test-session-123",
        head_yaw=15.5,
        head_pitch=-3.2,
        anomaly_score=0.3,
    )

    pub._redis.publish.assert_called_once()
    call_args = pub._redis.publish.call_args
    assert call_args[0][0] == CHANNEL_GAZE
    payload = json.loads(call_args[0][1])
    assert payload["head_yaw"] == 15.5
    assert payload["head_pitch"] == -3.2


@pytest.mark.asyncio
async def test_publisher_close():
    """Publisher close should close the Redis connection."""
    pub = RedisEventPublisher()
    pub._redis = AsyncMock()
    await pub.close()
    pub._redis.close.assert_called_once()

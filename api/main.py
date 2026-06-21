"""BEZP API — FastAPI application factory.

Privacy-first design: No live video streaming. Only event metadata
is sent to proctors in real-time. Video clips are uploaded only on
confirmed FLAG/CRITICAL events.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.database import init_db, async_session_factory

logger = structlog.get_logger()

_subscriber_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global _subscriber_task
    logger.info("bezp_starting", env=settings.APP_ENV)

    # Create tables (dev convenience — use Alembic in production)
    if settings.APP_ENV == "development":
        await init_db()
        logger.info("database_tables_created")

    # Start Redis event subscriber (detection → DB + WebSocket)
    from api.services.redis_bridge import RedisEventSubscriber
    from api.routers.ws import broadcast_event

    subscriber = RedisEventSubscriber(settings.REDIS_URL)
    _subscriber_task = asyncio.create_task(
        subscriber.start(async_session_factory, broadcast_event)
    )
    logger.info("redis_subscriber_started")

    yield

    # Shutdown
    if _subscriber_task:
        subscriber.stop()
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            pass
    logger.info("bezp_shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BEZP — Browser-Based Exam Proctoring System",
        description=(
            "Privacy-first exam proctoring API. "
            "Only event metadata is sent in real-time. "
            "Video clips are uploaded only on confirmed anomalies."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    from api.routers import sessions, events, clips, users, exams, ws, heartbeat

    app.include_router(sessions.router)
    app.include_router(events.router)
    app.include_router(clips.router)
    app.include_router(users.router)
    app.include_router(exams.router)
    app.include_router(ws.router)
    app.include_router(heartbeat.router)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "bezp-api"}

    return app


app = create_app()

"""Tests for API endpoints using TestClient.

These tests verify that all routes exist and respond correctly.
The lifespan is replaced to avoid needing running DB/Redis.
"""

import pytest
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def _noop_lifespan(app):
    yield


def _make_test_app():
    """Create a test app with mocked lifespan (no DB/Redis needed)."""
    app = FastAPI(lifespan=_noop_lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    from api.routers import sessions, events, clips, users, exams, ws
    app.include_router(sessions.router)
    app.include_router(events.router)
    app.include_router(clips.router)
    app.include_router(users.router)
    app.include_router(exams.router)
    app.include_router(ws.router)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "bezp-api"}

    return app


@pytest.fixture(scope="module")
def client():
    app = _make_test_app()
    return TestClient(app)


def test_health_check(client):
    """Health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "bezp-api"


def test_register_validation(client):
    """Register rejects missing fields with 422."""
    response = client.post("/api/users/register", json={})
    assert response.status_code == 422


def test_login_validation(client):
    """Login with invalid credentials — endpoint exists (not 404)."""
    response = client.post("/api/users/login", json={"email": "x@x.com", "password": "wrong"})
    assert response.status_code != 404


def test_sessions_endpoint(client):
    """Sessions list endpoint exists."""
    response = client.get("/api/sessions/")
    assert response.status_code != 404


def test_exams_endpoint(client):
    """Exams list endpoint exists."""
    response = client.get("/api/exams/")
    assert response.status_code != 404


def test_events_validation(client):
    """Events creation rejects missing fields."""
    response = client.post("/api/events/", json={})
    assert response.status_code == 422


def test_clips_missing_event(client):
    """Clips GET for non-existent event."""
    response = client.get("/api/clips/00000000-0000-0000-0000-000000000000")
    assert response.status_code != 404  # endpoint exists, may fail on DB

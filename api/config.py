"""BEZP API — Pydantic Settings configuration."""

from __future__ import annotations

import json
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──
    APP_NAME: str = "BEZP"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    CORS_ORIGINS: str = '["http://localhost:5173"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://bezp:bezp_secret@localhost:5432/bezp_db"

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── MinIO / S3 ──
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "bezp-clips"
    MINIO_USE_SSL: bool = False

    # ── JWT Auth ──
    JWT_SECRET: str = "change-me-to-a-random-64-char-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_LIFETIME_SECONDS: int = 3600

    # ── Detection Thresholds ──
    YOLO_CONFIDENCE_THRESHOLD: float = 0.5
    YOLO_FPS: int = 30  # Force YOLO on every frame in the pipeline
    PHONE_CONSECUTIVE_FRAMES: int = 1
    PERSON_CONSECUTIVE_FRAMES: int = 2
    NO_FACE_TIMEOUT_SECONDS: int = 5
    BACKGROUND_SSIM_THRESHOLD: float = 0.75
    BACKGROUND_CHECK_INTERVAL_MINUTES: int = 10
    IDENTITY_COSINE_THRESHOLD: float = 0.7
    GAZE_YAW_THRESHOLD: float = 30.0
    GAZE_PITCH_THRESHOLD: float = 20.0
    GAZE_ANOMALY_DURATION_SECONDS: int = 5
    TAB_SWITCH_FLAG_COUNT: int = 3
    TAB_SWITCH_FLAG_WINDOW_MINUTES: int = 2

    # ── Network ──
    NETWORK_PROBE_SIZE_KB: int = 100
    NETWORK_PROBE_INTERVAL_SECONDS: int = 30


settings = Settings()

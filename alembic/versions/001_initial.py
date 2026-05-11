"""Initial schema — all core tables.

Revision ID: 001_initial
Revises: None
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("student", "proctor", "admin", name="userrole"), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # ── exams ──
    op.create_table(
        "exams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_attempts", sa.Integer(), server_default="1"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("detection_config", postgresql.JSONB(), nullable=True),
        sa.Column("fl_enabled", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # ── exam_sessions ──
    op.create_table(
        "exam_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("exam_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exams.id"), nullable=False, index=True),
        sa.Column("status", sa.Enum("active", "paused", "completed", "terminated", name="sessionstatus"), server_default="active"),
        sa.Column("network_tier", sa.Enum("tier_1", "tier_2", "tier_3", "tier_4", name="networktier"), server_default="tier_1"),
        sa.Column("start_time", sa.DateTime(timezone=True)),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
    )

    # ── detection_events ──
    op.create_table(
        "detection_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exam_sessions.id"), nullable=False, index=True),
        sa.Column("event_type", sa.Enum(
            "phone_detected", "multiple_persons", "no_face", "identity_mismatch",
            "background_changed", "tab_switch", "fullscreen_exit", "window_blur",
            "gaze_anomaly", "coached_answer", name="eventtype"), nullable=False),
        sa.Column("tier", sa.Enum("info", "warning", "flag", "critical", name="eventtier"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True)),
        sa.Column("clip_url", sa.String(1024), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
    )

    # ── gaze_snapshots ──
    op.create_table(
        "gaze_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("exam_sessions.id"), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True)),
        sa.Column("gaze_x", sa.Float(), nullable=True),
        sa.Column("gaze_y", sa.Float(), nullable=True),
        sa.Column("head_yaw", sa.Float(), nullable=True),
        sa.Column("head_pitch", sa.Float(), nullable=True),
        sa.Column("blink_rate", sa.Float(), nullable=True),
        sa.Column("anomaly_score", sa.Float(), nullable=True),
    )

    # ── proctor_reviews ──
    op.create_table(
        "proctor_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("detection_events.id"), nullable=False, unique=True),
        sa.Column("proctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("verdict", sa.Enum("confirmed", "false_positive", "pending", name="reviewverdict"), server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("proctor_reviews")
    op.drop_table("gaze_snapshots")
    op.drop_table("detection_events")
    op.drop_table("exam_sessions")
    op.drop_table("exams")
    op.drop_table("users")
    for enum_name in ["userrole", "sessionstatus", "networktier", "eventtype", "eventtier", "reviewverdict"]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")

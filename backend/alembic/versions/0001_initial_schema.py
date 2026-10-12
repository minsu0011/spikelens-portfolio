"""Initial immutable PostgreSQL schema.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def identity():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def user_fk(name="owner_id", nullable=False):
    return sa.Column(
        name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable
    )


def upgrade():
    op.create_table(
        "users",
        identity(),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        created(),
        sa.CheckConstraint("role IN ('user','admin')", name="ck_user_role"),
    )
    op.create_table(
        "user_sessions",
        identity(),
        user_fk("user_id"),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        created(),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_table(
        "uploads",
        identity(),
        user_fk(),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        created(),
        sa.UniqueConstraint("owner_id", "sha256", name="uq_upload_owner_sha"),
    )
    op.create_index("ix_upload_owner_created", "uploads", ["owner_id", "created_at"])
    op.create_table(
        "events",
        identity(),
        user_fk(nullable=True),
        sa.Column(
            "upload_id", sa.Uuid(), sa.ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("p0_price", sa.Float(), nullable=False),
        sa.Column("t5_price", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("price_path", sa.JSON(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("data_quality_score", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False, unique=True),
        created(),
        sa.CheckConstraint("p0_price > 0 AND t5_price > 0 AND volume >= 0", name="ck_event_values"),
        sa.CheckConstraint("session IN ('PREMARKET','RTH','AFTERHOURS')", name="ck_event_session"),
        sa.CheckConstraint("NOT is_public OR owner_id IS NULL", name="ck_public_demo_owner"),
    )
    op.create_index("ix_event_public_time", "events", ["is_public", "event_time", "id"])
    op.create_index("ix_event_ticker_time", "events", ["ticker", "event_time", "id"])
    op.create_index("ix_event_session_time", "events", ["session", "event_time", "id"])
    op.create_index("ix_event_owner_time", "events", ["owner_id", "event_time"])
    op.create_table(
        "analysis_jobs",
        identity(),
        user_fk(),
        sa.Column(
            "upload_id", sa.Uuid(), sa.ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("processed_rows", sa.Integer(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.String(300), nullable=True),
        sa.Column("pending_dispatch", sa.Boolean(), nullable=False),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False),
        sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("celery_task_id", sa.String(80), nullable=True),
        created(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_job_owner_idempotency"),
        sa.UniqueConstraint("upload_id", "model_version", name="uq_job_upload_model"),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')", name="ck_job_status"
        ),
        sa.CheckConstraint(
            "processed_rows >= 0 AND processed_rows <= total_rows", name="ck_job_progress"
        ),
    )
    op.create_index("ix_job_owner_created", "analysis_jobs", ["owner_id", "created_at"])
    op.create_index("ix_job_status_created", "analysis_jobs", ["status", "created_at"])
    op.create_index("ix_job_dispatch", "analysis_jobs", ["pending_dispatch", "next_dispatch_at"])
    op.create_table(
        "analysis_results",
        identity(),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("data_quality_score", sa.Float(), nullable=False),
        sa.Column("event_summary", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        created(),
        sa.UniqueConstraint("job_id", "event_id", name="uq_result_job_event"),
    )
    op.create_table(
        "job_attempts",
        identity(),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.UniqueConstraint("job_id", "attempt", name="uq_job_attempt"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])
    op.create_table(
        "audit_logs",
        identity(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("resource_id", sa.String(80), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        created(),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade():
    for table in [
        "audit_logs",
        "job_attempts",
        "analysis_results",
        "analysis_jobs",
        "events",
        "uploads",
        "user_sessions",
        "users",
    ]:
        op.drop_table(table)

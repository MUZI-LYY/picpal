"""create conversation core tables

Revision ID: 20260821_0001
Revises: None
Create Date: 2026-08-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260821_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anonymous_sessions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_anonymous_sessions_token_hash"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "owner_session_id",
            sa.String(128),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requirements_json", sa.JSON(), nullable=False),
        sa.Column("latest_plan_id", sa.String(128), nullable=True),
        sa.Column("active_run_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('collecting_requirements','generating','completed','failed','archived')",
            name="ck_conversations_status",
        ),
    )
    op.create_index(
        "ix_conversations_owner_updated",
        "conversations",
        ["owner_session_id", "updated_at", "id"],
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(128),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_message_id", sa.String(128), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("structured_content_json", sa.JSON(), nullable=True),
        sa.Column("request_payload_json", sa.JSON(), nullable=True),
        sa.Column("reply_to_message_id", sa.String(128), nullable=True),
        sa.Column("run_id", sa.String(128), nullable=True),
        sa.Column("plan_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "conversation_id", "client_message_id", name="uq_messages_conversation_client_id"
        ),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        sa.CheckConstraint(
            "content_type IN ('text','clarification','run_started','plan_created','plan_updated','error')",
            name="ck_messages_content_type",
        ),
    )
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at", "id"]
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(128),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "trigger_message_id",
            sa.String(128),
            sa.ForeignKey("messages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("base_plan_id", sa.String(128), nullable=True),
        sa.Column("result_plan_id", sa.String(128), nullable=True),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column("requirements_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("revision_request_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('initial_plan','revision')", name="ck_runs_kind"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_runs_status"),
    )
    op.create_index("ix_runs_conversation_created", "runs", ["conversation_id", "created_at"])
    op.create_index(
        "uq_runs_active_per_conversation",
        "runs",
        ["conversation_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "run_stage_events",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "stage_key", name="uq_run_stage_key"),
        sa.CheckConstraint(
            "status IN ('waiting','running','succeeded','failed','skipped')",
            name="ck_run_stage_status",
        ),
    )
    op.create_table(
        "plan_versions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(128),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("base_plan_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("plan_schema_version", sa.String(32), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("changed_days_json", sa.JSON(), nullable=False),
        sa.Column("change_summary_json", sa.JSON(), nullable=False),
        sa.Column("knowledge_index_version", sa.String(128), nullable=False),
        sa.Column("retrieval_run_ids_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "conversation_id", "version", name="uq_plan_versions_conversation_version"
        ),
        sa.UniqueConstraint("run_id", name="uq_plan_versions_run"),
        sa.CheckConstraint("status = 'validated'", name="ck_plan_versions_validated"),
    )
    op.create_index(
        "ix_plan_versions_conversation_created",
        "plan_versions",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "retrieval_runs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("poi_id", sa.String(128), nullable=False),
        sa.Column("query_json", sa.JSON(), nullable=False),
        sa.Column("pipeline_json", sa.JSON(), nullable=False),
        sa.Column("candidate_trace_json", sa.JSON(), nullable=False),
        sa.Column("result_spot_ids_json", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_retrieval_runs_run_poi", "retrieval_runs", ["run_id", "poi_id"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_runs_run_poi", table_name="retrieval_runs")
    op.drop_table("retrieval_runs")
    op.drop_index("ix_plan_versions_conversation_created", table_name="plan_versions")
    op.drop_table("plan_versions")
    op.drop_table("run_stage_events")
    op.drop_index("uq_runs_active_per_conversation", table_name="runs")
    op.drop_index("ix_runs_conversation_created", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_owner_updated", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("anonymous_sessions")

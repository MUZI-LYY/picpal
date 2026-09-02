"""对话、消息、运行任务、行程版本和 RAG 追踪的 ORM 模型。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .errors import ImmutableRecordError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnonymousSessionModel(Base):
    __tablename__ = "anonymous_sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    invited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ConversationModel(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('collecting_requirements','generating','completed','failed','archived')",
            name="ck_conversations_status",
        ),
        Index("ix_conversations_owner_updated", "owner_session_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_session_id: Mapped[str] = mapped_column(
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="collecting_requirements")
    requirements_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    latest_plan_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active_run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "client_message_id", name="uq_messages_conversation_client_id"
        ),
        CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        CheckConstraint(
            "content_type IN ('text','clarification','run_started','plan_created','plan_updated','error')",
            name="ck_messages_content_type",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    client_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_content_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    request_payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    reply_to_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    plan_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RunModel(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("kind IN ('initial_plan','revision')", name="ck_runs_kind"),
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="ck_runs_status"),
        Index(
            "uq_runs_active_per_conversation",
            "conversation_id",
            unique=True,
            sqlite_where=text("status IN ('queued','running')"),
        ),
        Index("ix_runs_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    trigger_message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="RESTRICT"), nullable=False
    )
    base_plan_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    result_plan_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requirements_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    revision_request_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RunStageEventModel(Base):
    __tablename__ = "run_stage_events"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", name="uq_run_stage_key"),
        CheckConstraint(
            "status IN ('waiting','running','succeeded','failed','skipped')",
            name="ck_run_stage_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PlanVersionModel(Base):
    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("conversation_id", "version", name="uq_plan_versions_conversation_version"),
        UniqueConstraint("run_id", name="uq_plan_versions_run"),
        CheckConstraint("status = 'validated'", name="ck_plan_versions_validated"),
        Index("ix_plan_versions_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_plan_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="validated")
    plan_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    changed_days_json: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    change_summary_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    knowledge_index_version: Mapped[str] = mapped_column(String(128), nullable=False)
    retrieval_run_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RetrievalRunModel(Base):
    __tablename__ = "retrieval_runs"
    __table_args__ = (Index("ix_retrieval_runs_run_poi", "run_id", "poi_id"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    poi_id: Mapped[str] = mapped_column(String(128), nullable=False)
    query_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pipeline_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate_trace_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    result_spot_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


@event.listens_for(PlanVersionModel, "before_update", propagate=True)
def _prevent_plan_version_update(mapper, connection, target):  # noqa: ANN001, ARG001
    raise ImmutableRecordError("PlanVersion 不允许更新")


@event.listens_for(PlanVersionModel, "before_delete", propagate=True)
def _prevent_plan_version_delete(mapper, connection, target):  # noqa: ANN001, ARG001
    raise ImmutableRecordError("PlanVersion 不允许删除")

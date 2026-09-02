"""对话式核心实体的 Repository。方法只 flush，不替调用方 commit。"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .errors import ActiveRunConflict, IdempotencyConflict
from .models import (
    AnonymousSessionModel,
    ConversationModel,
    MessageModel,
    PlanVersionModel,
    RunModel,
    RunStageEventModel,
    utcnow,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _encode_cursor(updated_at: datetime, record_id: str) -> str:
    raw = json.dumps(
        {"updated_at": updated_at.isoformat(), "id": record_id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return datetime.fromisoformat(data["updated_at"]), str(data["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("无效游标") from exc


class AnonymousSessionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, *, token_hash: str) -> AnonymousSessionModel:
        existing = self.session.scalar(
            select(AnonymousSessionModel).where(AnonymousSessionModel.token_hash == token_hash)
        )
        if existing is not None:
            existing.last_seen_at = utcnow()
            self.session.flush()
            return existing
        record = AnonymousSessionModel(id=_new_id("anon"), token_hash=token_hash)
        self.session.add(record)
        self.session.flush()
        return record


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        owner_session_id: str,
        title: str,
        requirements: dict[str, Any],
    ) -> ConversationModel:
        record = ConversationModel(
            id=_new_id("conv"),
            owner_session_id=owner_session_id,
            title=title,
            status="collecting_requirements",
            requirements_json=requirements,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_owned(self, conversation_id: str, owner_session_id: str) -> Optional[ConversationModel]:
        return self.session.scalar(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.owner_session_id == owner_session_id,
            )
        )

    def get_by_owner_client_message(
        self, owner_session_id: str, client_message_id: str
    ) -> Optional[ConversationModel]:
        return self.session.scalar(
            select(ConversationModel)
            .join(MessageModel, MessageModel.conversation_id == ConversationModel.id)
            .where(
                ConversationModel.owner_session_id == owner_session_id,
                MessageModel.client_message_id == client_message_id,
                MessageModel.role == "user",
            )
        )

    def update_requirements(
        self,
        conversation: ConversationModel,
        *,
        requirements: dict[str, Any],
    ) -> ConversationModel:
        conversation.requirements_json = requirements
        conversation.status = "collecting_requirements"
        conversation.updated_at = utcnow()
        self.session.flush()
        return conversation

    def list_owned(
        self,
        owner_session_id: str,
        *,
        limit: int,
        cursor: Optional[str] = None,
    ) -> tuple[list[ConversationModel], Optional[str]]:
        if not 1 <= limit <= 50:
            raise ValueError("limit 必须在 1 到 50 之间")
        statement = select(ConversationModel).where(
            ConversationModel.owner_session_id == owner_session_id
        )
        if cursor:
            updated_at, record_id = _decode_cursor(cursor)
            statement = statement.where(
                or_(
                    ConversationModel.updated_at < updated_at,
                    and_(
                        ConversationModel.updated_at == updated_at,
                        ConversationModel.id < record_id,
                    ),
                )
            )
        statement = statement.order_by(
            ConversationModel.updated_at.desc(), ConversationModel.id.desc()
        ).limit(limit + 1)
        records = list(self.session.scalars(statement))
        has_next = len(records) > limit
        items = records[:limit]
        next_cursor = _encode_cursor(items[-1].updated_at, items[-1].id) if has_next else None
        return items, next_cursor


class MessageRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_user(
        self,
        *,
        conversation_id: str,
        client_message_id: str,
        text: str,
        reply_to_message_id: Optional[str],
        structured_answer: Optional[dict[str, Any]],
        base_plan_id: Optional[str],
    ) -> MessageModel:
        payload = {
            "text": text,
            "reply_to_message_id": reply_to_message_id,
            "structured_answer": structured_answer,
            "base_plan_id": base_plan_id,
        }
        existing = self.session.scalar(
            select(MessageModel).where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.client_message_id == client_message_id,
            )
        )
        if existing is not None:
            if existing.request_payload_json != payload:
                raise IdempotencyConflict("client_message_id 已用于不同请求")
            return existing
        record = MessageModel(
            id=_new_id("msg"),
            conversation_id=conversation_id,
            client_message_id=client_message_id,
            role="user",
            content_type="text",
            text=text,
            structured_content_json=None,
            request_payload_json=payload,
            reply_to_message_id=reply_to_message_id,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, message_id: str) -> Optional[MessageModel]:
        return self.session.get(MessageModel, message_id)

    def get_user_by_client_id(
        self, conversation_id: str, client_message_id: str
    ) -> Optional[MessageModel]:
        return self.session.scalar(
            select(MessageModel).where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.client_message_id == client_message_id,
                MessageModel.role == "user",
            )
        )

    def list_replies(self, conversation_id: str, message_id: str) -> list[MessageModel]:
        return list(
            self.session.scalars(
                select(MessageModel)
                .where(
                    MessageModel.conversation_id == conversation_id,
                    MessageModel.reply_to_message_id == message_id,
                    MessageModel.role == "assistant",
                )
                .order_by(MessageModel.created_at, MessageModel.id)
            )
        )

    def has_user_reply(self, conversation_id: str, message_id: str) -> bool:
        return (
            self.session.scalar(
                select(MessageModel.id).where(
                    MessageModel.conversation_id == conversation_id,
                    MessageModel.reply_to_message_id == message_id,
                    MessageModel.role == "user",
                )
            )
            is not None
        )

    def create_assistant(
        self,
        *,
        conversation_id: str,
        content_type: str,
        text: str,
        structured_content: dict[str, Any],
        reply_to_message_id: str,
        run_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> MessageModel:
        record = MessageModel(
            id=_new_id("msg"),
            conversation_id=conversation_id,
            client_message_id=None,
            role="assistant",
            content_type=content_type,
            text=text,
            structured_content_json=structured_content,
            request_payload_json=None,
            reply_to_message_id=reply_to_message_id,
            run_id=run_id,
            plan_id=plan_id,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def latest_user_preview(self, conversation_id: str, *, max_length: int = 300) -> str:
        value = self.session.scalar(
            select(MessageModel.text)
            .where(
                MessageModel.conversation_id == conversation_id,
                MessageModel.role == "user",
            )
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(1)
        )
        return (value or "")[:max_length]

    def list_recent(
        self, conversation_id: str, *, limit: int = 50
    ) -> tuple[list[MessageModel], bool, Optional[str]]:
        records = list(
            self.session.scalars(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(limit + 1)
            )
        )
        has_more = len(records) > limit
        items = list(reversed(records[:limit]))
        before_cursor = items[0].id if has_more and items else None
        return items, has_more, before_cursor


class RunRepository:
    ACTIVE_STATUSES = ("queued", "running")

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        conversation_id: str,
        kind: str,
        trigger_message_id: str,
        base_plan_id: Optional[str],
        requirements_snapshot: dict[str, Any],
        revision_request: Optional[dict[str, Any]],
    ) -> RunModel:
        active = self.session.scalar(
            select(RunModel.id).where(
                RunModel.conversation_id == conversation_id,
                RunModel.status.in_(self.ACTIVE_STATUSES),
            )
        )
        if active is not None:
            raise ActiveRunConflict("Conversation 已有运行中的 Run")
        record = RunModel(
            id=_new_id("run"),
            conversation_id=conversation_id,
            kind=kind,
            status="queued",
            trigger_message_id=trigger_message_id,
            base_plan_id=base_plan_id,
            requirements_snapshot_json=requirements_snapshot,
            revision_request_json=revision_request,
        )
        conversation = self.session.get(ConversationModel, conversation_id)
        if conversation is None:
            raise ValueError("Conversation 不存在")
        conversation.status = "generating"
        conversation.active_run_id = record.id
        conversation.updated_at = utcnow()
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_trigger_message(self, conversation_id: str, message_id: str) -> Optional[RunModel]:
        return self.session.scalar(
            select(RunModel).where(
                RunModel.conversation_id == conversation_id,
                RunModel.trigger_message_id == message_id,
            )
        )

    def get(self, run_id: str) -> Optional[RunModel]:
        return self.session.get(RunModel, run_id)

    def get_owned(self, run_id: str, owner_session_id: str) -> Optional[RunModel]:
        return self.session.scalar(
            select(RunModel)
            .join(ConversationModel, ConversationModel.id == RunModel.conversation_id)
            .where(
                RunModel.id == run_id,
                ConversationModel.owner_session_id == owner_session_id,
            )
        )

    def mark_running(self, run_id: str) -> RunModel:
        run = self.session.get(RunModel, run_id)
        if run is None:
            raise ValueError("Run 不存在")
        run.status = "running"
        run.started_at = utcnow()
        self.session.flush()
        return run

    def set_stage(self, run_id: str, stage_key: str) -> RunModel:
        run = self.session.get(RunModel, run_id)
        if run is None:
            raise ValueError("Run 不存在")
        run.current_stage = stage_key
        self.session.flush()
        return run

    def finish_failed(self, run_id: str, *, code: str, message: str) -> RunModel:
        run = self.session.get(RunModel, run_id)
        if run is None:
            raise ValueError("Run 不存在")
        run.status = "failed"
        run.error_code = code
        run.error_message = message
        run.finished_at = utcnow()
        conversation = self.session.get(ConversationModel, run.conversation_id)
        if conversation is None:
            raise ValueError("Conversation 不存在")
        conversation.active_run_id = None
        conversation.status = "completed" if conversation.latest_plan_id else "failed"
        conversation.updated_at = utcnow()
        self.session.flush()
        return run


class RunStageEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def seed(self, run_id: str, stage_keys: list[str]) -> None:
        existing = self.session.scalars(
            select(RunStageEventModel).where(RunStageEventModel.run_id == run_id)
        ).all()
        if existing:
            return
        for sequence, key in enumerate(stage_keys):
            self.session.add(
                RunStageEventModel(
                    id=_new_id("rse"),
                    run_id=run_id,
                    stage_key=key,
                    status="waiting",
                    sequence=sequence,
                )
            )
        self.session.flush()

    def _get(self, run_id: str, stage_key: str) -> Optional[RunStageEventModel]:
        return self.session.scalar(
            select(RunStageEventModel).where(
                RunStageEventModel.run_id == run_id,
                RunStageEventModel.stage_key == stage_key,
            )
        )

    def start(self, run_id: str, stage_key: str) -> None:
        record = self._get(run_id, stage_key)
        if record is not None:
            record.status = "running"
            record.started_at = utcnow()
            self.session.flush()

    def complete(self, run_id: str, stage_key: str) -> None:
        record = self._get(run_id, stage_key)
        if record is not None:
            record.status = "succeeded"
            record.completed_at = utcnow()
            self.session.flush()

    def fail(self, run_id: str, stage_key: str) -> None:
        record = self._get(run_id, stage_key)
        if record is not None:
            record.status = "failed"
            record.completed_at = utcnow()
            self.session.flush()

    def list_for(self, run_id: str) -> list[RunStageEventModel]:
        return list(
            self.session.scalars(
                select(RunStageEventModel)
                .where(RunStageEventModel.run_id == run_id)
                .order_by(RunStageEventModel.sequence)
            )
        )


class PlanVersionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, plan_id: str) -> Optional[PlanVersionModel]:
        return self.session.get(PlanVersionModel, plan_id)

    def get_owned(self, plan_id: str, owner_session_id: str) -> Optional[PlanVersionModel]:
        return self.session.scalar(
            select(PlanVersionModel)
            .join(ConversationModel, ConversationModel.id == PlanVersionModel.conversation_id)
            .where(
                PlanVersionModel.id == plan_id,
                ConversationModel.owner_session_id == owner_session_id,
            )
        )

    def create_validated(
        self,
        *,
        conversation_id: str,
        run_id: str,
        base_plan_id: Optional[str],
        plan_schema_version: str,
        plan: dict[str, Any],
        changed_days: list[int],
        change_summary: list[str],
        knowledge_index_version: str,
        retrieval_run_ids: list[str],
    ) -> PlanVersionModel:
        if not changed_days:
            raise ValueError("changed_days 不能为空")
        current_version = self.session.scalar(
            select(func.max(PlanVersionModel.version)).where(
                PlanVersionModel.conversation_id == conversation_id
            )
        )
        plan_id = _new_id("plan")
        plan_snapshot = dict(plan)
        plan_snapshot["plan_id"] = plan_id
        record = PlanVersionModel(
            id=plan_id,
            conversation_id=conversation_id,
            run_id=run_id,
            version=(current_version or 0) + 1,
            base_plan_id=base_plan_id,
            status="validated",
            plan_schema_version=plan_schema_version,
            plan_json=plan_snapshot,
            changed_days_json=list(changed_days),
            change_summary_json=list(change_summary),
            knowledge_index_version=knowledge_index_version,
            retrieval_run_ids_json=list(retrieval_run_ids),
        )
        run = self.session.get(RunModel, run_id)
        conversation = self.session.get(ConversationModel, conversation_id)
        if run is None or conversation is None:
            raise ValueError("Run 或 Conversation 不存在")
        run.status = "succeeded"
        run.result_plan_id = plan_id
        run.error_code = None
        run.error_message = None
        run.finished_at = utcnow()
        conversation.latest_plan_id = plan_id
        conversation.active_run_id = None
        conversation.status = "completed"
        conversation.updated_at = utcnow()
        self.session.add(record)
        self.session.flush()
        return record

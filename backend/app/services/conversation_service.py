"""对话轮次的事务型应用服务。调用方负责 commit/rollback。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import ConversationModel, MessageModel, RunModel
from ..db.repositories import (
    ConversationRepository,
    MessageRepository,
    RunRepository,
)
from ..schemas.conversation import ClarificationContent, RequirementsSnapshot
from .requirement_collector import RequirementCollector

_TITLE_COMPANIONS = ("情侣", "亲子", "朋友", "独自")
_INTEREST_LABELS = {
    "经典景点": "经典",
    "历史建筑": "历史",
    "胡同": "胡同",
    "自然风景": "自然",
    "城市景观": "夜景",
}


class ConversationServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ConversationTurn:
    conversation: ConversationModel
    accepted_message: MessageModel
    assistant_messages: list[MessageModel]
    active_run: RunModel | None
    latest_plan: None = None


class ConversationService:
    def __init__(
        self,
        session: Session,
        *,
        collector: RequirementCollector | None = None,
        intent_parser=None,
    ):
        self.session = session
        self.collector = collector or RequirementCollector(intent_parser=intent_parser)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.runs = RunRepository(session)

    def create_conversation(
        self,
        *,
        owner_session_id: str,
        client_message_id: str,
        text: str,
    ) -> ConversationTurn:
        collected = self.collector.collect(text)
        conversation = self.conversations.create(
            owner_session_id=owner_session_id,
            title=self._title(collected.requirements),
            requirements=collected.requirements.model_dump(mode="json"),
        )
        user_message = self.messages.create_user(
            conversation_id=conversation.id,
            client_message_id=client_message_id,
            text=text,
            reply_to_message_id=None,
            structured_answer=None,
            base_plan_id=None,
        )
        return self._complete_turn(
            conversation=conversation,
            user_message=user_message,
            requirements=collected.requirements,
            clarification=collected.clarification,
        )

    def create_message(
        self,
        *,
        owner_session_id: str,
        conversation_id: str,
        client_message_id: str,
        text: str,
        reply_to_message_id: str | None,
        structured_answer: dict[str, Any] | None,
        base_plan_id: str | None,
    ) -> ConversationTurn:
        conversation = self.conversations.get_owned(conversation_id, owner_session_id)
        if conversation is None:
            raise ConversationServiceError("not_found", "对话不存在")

        existing = self.messages.get_user_by_client_id(conversation.id, client_message_id)
        if existing is not None:
            accepted = self.messages.create_user(
                conversation_id=conversation.id,
                client_message_id=client_message_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                structured_answer=structured_answer,
                base_plan_id=base_plan_id,
            )
            return self._replay_turn(conversation, accepted)

        if conversation.active_run_id is not None:
            raise ConversationServiceError("run_in_progress", "当前对话已有运行中的任务")
        if base_plan_id is not None:
            raise ConversationServiceError(
                "plan_version_conflict", "需求补齐阶段不能提交 base_plan_id"
            )

        self._validate_structured_reply(
            conversation_id=conversation.id,
            reply_to_message_id=reply_to_message_id,
            structured_answer=structured_answer,
        )
        collected = self.collector.collect(
            text,
            current=conversation.requirements_json,
            structured_answer=structured_answer,
        )
        user_message = self.messages.create_user(
            conversation_id=conversation.id,
            client_message_id=client_message_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            structured_answer=structured_answer,
            base_plan_id=base_plan_id,
        )
        self.conversations.update_requirements(
            conversation,
            requirements=collected.requirements.model_dump(mode="json"),
        )
        conversation.title = self._title(collected.requirements)
        return self._complete_turn(
            conversation=conversation,
            user_message=user_message,
            requirements=collected.requirements,
            clarification=collected.clarification,
        )

    def _complete_turn(
        self,
        *,
        conversation: ConversationModel,
        user_message: MessageModel,
        requirements: RequirementsSnapshot,
        clarification: ClarificationContent | None,
    ) -> ConversationTurn:
        if clarification is not None:
            assistant = self.messages.create_assistant(
                conversation_id=conversation.id,
                content_type="clarification",
                text=self._clarification_text(clarification.slot),
                structured_content=clarification.model_dump(mode="json"),
                reply_to_message_id=user_message.id,
            )
            return ConversationTurn(conversation, user_message, [assistant], None)

        run = self.runs.create(
            conversation_id=conversation.id,
            kind="initial_plan",
            trigger_message_id=user_message.id,
            base_plan_id=None,
            requirements_snapshot=requirements.model_dump(mode="json"),
            revision_request=None,
        )
        assistant = self.messages.create_assistant(
            conversation_id=conversation.id,
            content_type="run_started",
            text="信息已确认，正在为你生成北京旅行计划。",
            structured_content={"kind": "run_started", "run_id": run.id},
            reply_to_message_id=user_message.id,
            run_id=run.id,
        )
        return ConversationTurn(conversation, user_message, [assistant], run)

    def _validate_structured_reply(
        self,
        *,
        conversation_id: str,
        reply_to_message_id: str | None,
        structured_answer: dict[str, Any] | None,
    ) -> None:
        if structured_answer is None:
            return
        if reply_to_message_id is None:
            raise ConversationServiceError("invalid_slot_value", "结构化回答必须关联追问消息")
        question = self.messages.get(reply_to_message_id)
        if (
            question is None
            or question.conversation_id != conversation_id
            or question.role != "assistant"
            or question.content_type != "clarification"
            or not question.structured_content_json
        ):
            raise ConversationServiceError("invalid_slot_value", "回复的追问消息无效")
        if question.structured_content_json.get("slot") != structured_answer.get("slot"):
            raise ConversationServiceError("invalid_slot_value", "回答槽位与追问不匹配")
        if self.messages.has_user_reply(conversation_id, question.id):
            raise ConversationServiceError(
                "clarification_already_answered", "该追问已经回答"
            )

    def _replay_turn(
        self, conversation: ConversationModel, accepted_message: MessageModel
    ) -> ConversationTurn:
        assistant_messages = self.messages.list_replies(
            conversation.id, accepted_message.id
        )
        if not assistant_messages:
            raise ConversationServiceError("internal_error", "原对话轮次不完整")
        active_run = self.runs.get_by_trigger_message(
            conversation.id, accepted_message.id
        )
        return ConversationTurn(
            conversation,
            accepted_message,
            assistant_messages,
            active_run,
        )

    @staticmethod
    def _title(requirements: RequirementsSnapshot) -> str:
        if requirements.days is None:
            return "新的北京旅行计划"
        day = f"{requirements.days}天"
        subject = next(
            (c for c in requirements.companion_types if c in _TITLE_COMPANIONS),
            "北京",
        )
        theme = next(
            (_INTEREST_LABELS[i] for i in requirements.interests if i in _INTEREST_LABELS),
            None,
        )
        if theme:
            return f"{subject}{theme}旅行{day}"
        if requirements.pace in ("轻松", "紧凑"):
            return f"{subject}{requirements.pace}游{day}"
        return f"{subject}{day}"

    @staticmethod
    def _clarification_text(slot: str) -> str:
        if slot == "days":
            return "这次准备在北京玩几天？"
        if slot == "start_date":
            return "出发日期定了吗？也可以先选择日期待定。"
        return "你更偏向哪种旅行节奏？"

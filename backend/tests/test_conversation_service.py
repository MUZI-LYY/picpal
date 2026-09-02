"""ConversationService 的事务型多轮对话测试。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import pytest

from app.db.base import Base
from app.db.models import MessageModel, RunModel
from app.db.repositories import AnonymousSessionRepository
from app.db.session import create_sqlite_engine
from app.services.conversation_service import ConversationService, ConversationServiceError


@pytest.fixture()
def db(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'conversation-service.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _owner(factory, token_hash="token-a"):
    with factory.begin() as session:
        return AnonymousSessionRepository(session).create(token_hash=token_hash)


def test_create_conversation_persists_user_and_days_clarification_atomically(db):
    owner = _owner(db)
    with db.begin() as session:
        turn = ConversationService(session).create_conversation(
            owner_session_id=owner.id,
            client_message_id="client-1",
            text="第一次去北京，想走经典路线，每天别太赶",
        )

        assert turn.conversation.status == "collecting_requirements"
        assert turn.conversation.requirements_json["days"] is None
        assert turn.accepted_message.role == "user"
        assert len(turn.assistant_messages) == 1
        clarification = turn.assistant_messages[0]
        assert clarification.content_type == "clarification"
        assert clarification.reply_to_message_id == turn.accepted_message.id
        assert clarification.structured_content_json["slot"] == "days"
        assert turn.active_run is None

    with db() as session:
        assert session.scalar(select(func.count()).select_from(MessageModel)) == 2
        assert session.scalar(select(func.count()).select_from(RunModel)) == 0


def test_answering_days_then_pending_date_creates_initial_run(db):
    owner = _owner(db)
    with db.begin() as session:
        service = ConversationService(session)
        first = service.create_conversation(
            owner_session_id=owner.id,
            client_message_id="client-1",
            text="第一次去北京，想拍经典机位",
        )
        days_question = first.assistant_messages[0]
        second = service.create_message(
            owner_session_id=owner.id,
            conversation_id=first.conversation.id,
            client_message_id="client-2",
            text="3 天",
            reply_to_message_id=days_question.id,
            structured_answer={"slot": "days", "value": 3},
            base_plan_id=None,
        )
        assert second.active_run is None
        assert second.assistant_messages[0].structured_content_json["slot"] == "start_date"

        date_question = second.assistant_messages[0]
        third = service.create_message(
            owner_session_id=owner.id,
            conversation_id=first.conversation.id,
            client_message_id="client-3",
            text="日期待定",
            reply_to_message_id=date_question.id,
            structured_answer={"slot": "start_date", "value": "pending"},
            base_plan_id=None,
        )
        assert third.active_run is None
        assert third.assistant_messages[0].structured_content_json["slot"] == "pace"

        pace_question = third.assistant_messages[0]
        fourth = service.create_message(
            owner_session_id=owner.id,
            conversation_id=first.conversation.id,
            client_message_id="client-4",
            text="轻松",
            reply_to_message_id=pace_question.id,
            structured_answer={"slot": "pace", "value": "轻松"},
            base_plan_id=None,
        )

        assert fourth.conversation.status == "generating"
        assert fourth.conversation.requirements_json["date_status"] == "pending"
        assert fourth.conversation.requirements_json["pace"] == "轻松"
        assert fourth.active_run.status == "queued"
        assert fourth.active_run.trigger_message_id == fourth.accepted_message.id
        assert fourth.assistant_messages[0].content_type == "run_started"
        assert fourth.assistant_messages[0].run_id == fourth.active_run.id


def test_complete_first_message_starts_run_without_clarification(db):
    owner = _owner(db)
    with db.begin() as session:
        turn = ConversationService(session).create_conversation(
            owner_session_id=owner.id,
            client_message_id="client-complete",
            text="2026年10月1日去北京玩两天，想拍夜景，轻松",
        )

        assert turn.active_run is not None
        assert turn.conversation.active_run_id == turn.active_run.id
        assert turn.assistant_messages[0].structured_content_json == {
            "kind": "run_started",
            "run_id": turn.active_run.id,
        }


def test_same_client_message_retry_replays_original_turn_without_duplicates(db):
    owner = _owner(db)
    with db.begin() as session:
        service = ConversationService(session)
        first = service.create_conversation(
            owner_session_id=owner.id,
            client_message_id="client-1",
            text="北京玩两天，日期待定，轻松",
        )
        retried = service.create_message(
            owner_session_id=owner.id,
            conversation_id=first.conversation.id,
            client_message_id="client-1",
            text="北京玩两天，日期待定，轻松",
            reply_to_message_id=None,
            structured_answer=None,
            base_plan_id=None,
        )

        assert retried.accepted_message.id == first.accepted_message.id
        assert retried.assistant_messages[0].id == first.assistant_messages[0].id
        assert retried.active_run.id == first.active_run.id
        assert session.scalar(select(func.count()).select_from(MessageModel)) == 2
        assert session.scalar(select(func.count()).select_from(RunModel)) == 1


def test_structured_answer_must_reply_to_matching_open_clarification(db):
    owner = _owner(db)
    with db.begin() as session:
        service = ConversationService(session)
        first = service.create_conversation(
            owner_session_id=owner.id,
            client_message_id="client-1",
            text="想去北京拍照",
        )
        with pytest.raises(ConversationServiceError) as error:
            service.create_message(
                owner_session_id=owner.id,
                conversation_id=first.conversation.id,
                client_message_id="client-bad",
                text="日期待定",
                reply_to_message_id=first.assistant_messages[0].id,
                structured_answer={"slot": "start_date", "value": "pending"},
                base_plan_id=None,
            )

        assert error.value.code == "invalid_slot_value"
        assert session.scalar(select(func.count()).select_from(MessageModel)) == 2


def test_foreign_owner_cannot_continue_conversation(db):
    owner_a = _owner(db, "token-a")
    owner_b = _owner(db, "token-b")
    with db.begin() as session:
        first = ConversationService(session).create_conversation(
            owner_session_id=owner_a.id,
            client_message_id="client-1",
            text="想去北京拍照",
        )

    with db.begin() as session:
        with pytest.raises(ConversationServiceError) as error:
            ConversationService(session).create_message(
                owner_session_id=owner_b.id,
                conversation_id=first.conversation.id,
                client_message_id="client-2",
                text="3 天",
                reply_to_message_id=first.assistant_messages[0].id,
                structured_answer={"slot": "days", "value": 3},
                base_plan_id=None,
            )

        assert error.value.code == "not_found"

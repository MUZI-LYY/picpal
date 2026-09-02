"""Conversation/Message/Run/PlanVersion 数据层行为测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.errors import ActiveRunConflict, IdempotencyConflict, ImmutableRecordError
from app.db.models import ConversationModel, MessageModel, PlanVersionModel, RunModel
from app.db.repositories import (
    AnonymousSessionRepository,
    ConversationRepository,
    MessageRepository,
    PlanVersionRepository,
    RunRepository,
)
from app.db.session import create_sqlite_engine


@pytest.fixture()
def db(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _requirements(days=None, date_status="unknown", start_date=None):
    return {
        "city": "北京",
        "days": days,
        "date_status": date_status,
        "start_date": start_date,
        "party_size": None,
        "companion_types": [],
        "must_include": [],
        "must_exclude": [],
        "interests": [],
        "photo_preferences": [],
        "pace": None,
        "lodging_text": None,
        "transport_preferences": [],
        "missing_slots": ["days", "start_date"] if days is None else ["start_date"],
    }


def _conversation(session: Session, token_hash="token-a"):
    owner = AnonymousSessionRepository(session).create(token_hash=token_hash)
    return ConversationRepository(session).create(
        owner_session_id=owner.id,
        title="新的北京旅行计划",
        requirements=_requirements(),
    )


def _user_message(session: Session, conversation_id: str, client_id="client-1", text_="三天"):
    return MessageRepository(session).create_user(
        conversation_id=conversation_id,
        client_message_id=client_id,
        text=text_,
        reply_to_message_id=None,
        structured_answer=None,
        base_plan_id=None,
    )


def test_sqlite_engine_enables_foreign_keys_wal_and_busy_timeout(db):
    engine, _ = db
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() >= 5000


def test_conversation_is_scoped_to_anonymous_owner(db):
    _, factory = db
    with factory.begin() as session:
        owner_a = AnonymousSessionRepository(session).create(token_hash="token-a")
        owner_b = AnonymousSessionRepository(session).create(token_hash="token-b")
        conversation = ConversationRepository(session).create(
            owner_session_id=owner_a.id,
            title="北京三日游",
            requirements=_requirements(3, "pending"),
        )
        repository = ConversationRepository(session)
        assert repository.get_owned(conversation.id, owner_a.id).id == conversation.id
        assert repository.get_owned(conversation.id, owner_b.id) is None


def test_conversation_history_uses_stable_cursor_pagination(db):
    _, factory = db
    with factory.begin() as session:
        owner = AnonymousSessionRepository(session).create(token_hash="token-a")
        repository = ConversationRepository(session)
        base = datetime(2026, 8, 21, tzinfo=timezone.utc)
        created = []
        for index in range(3):
            conversation = repository.create(
                owner_session_id=owner.id,
                title=f"计划 {index}",
                requirements=_requirements(),
            )
            conversation.updated_at = base + timedelta(minutes=index)
            created.append(conversation)
        session.flush()

        first_page, cursor = repository.list_owned(owner.id, limit=2)
        second_page, next_cursor = repository.list_owned(owner.id, limit=2, cursor=cursor)

        assert [item.id for item in first_page] == [created[2].id, created[1].id]
        assert [item.id for item in second_page] == [created[0].id]
        assert cursor is not None
        assert next_cursor is None


def test_user_message_retries_are_idempotent(db):
    _, factory = db
    with factory.begin() as session:
        conversation = _conversation(session)
        repository = MessageRepository(session)
        first = repository.create_user(
            conversation_id=conversation.id,
            client_message_id="client-1",
            text="三天",
            reply_to_message_id=None,
            structured_answer={"slot": "days", "value": 3},
            base_plan_id=None,
        )
        retried = repository.create_user(
            conversation_id=conversation.id,
            client_message_id="client-1",
            text="三天",
            reply_to_message_id=None,
            structured_answer={"slot": "days", "value": 3},
            base_plan_id=None,
        )
        assert retried.id == first.id
        assert session.scalar(select(func.count()).select_from(MessageModel)) == 1


def test_reusing_client_message_id_with_different_payload_fails(db):
    _, factory = db
    with factory.begin() as session:
        conversation = _conversation(session)
        repository = MessageRepository(session)
        _user_message(session, conversation.id, client_id="client-1", text_="三天")
        with pytest.raises(IdempotencyConflict):
            _user_message(session, conversation.id, client_id="client-1", text_="两天")


def test_only_one_active_run_is_allowed_per_conversation(db):
    _, factory = db
    with factory.begin() as session:
        conversation = _conversation(session)
        message = _user_message(session, conversation.id)
        repository = RunRepository(session)
        first = repository.create(
            conversation_id=conversation.id,
            kind="initial_plan",
            trigger_message_id=message.id,
            base_plan_id=None,
            requirements_snapshot=_requirements(3, "pending"),
            revision_request=None,
        )
        with pytest.raises(ActiveRunConflict):
            repository.create(
                conversation_id=conversation.id,
                kind="revision",
                trigger_message_id=message.id,
                base_plan_id="plan-old",
                requirements_snapshot=_requirements(3, "pending"),
                revision_request={"text": "第二天轻松一点"},
            )
        repository.finish_failed(first.id, code="validation_failed", message="未通过校验")
        second = repository.create(
            conversation_id=conversation.id,
            kind="revision",
            trigger_message_id=message.id,
            base_plan_id="plan-old",
            requirements_snapshot=_requirements(3, "pending"),
            revision_request={"text": "第二天轻松一点"},
        )
        assert second.id != first.id


def test_plan_versions_increment_and_are_immutable(db):
    _, factory = db
    with factory.begin() as session:
        conversation = _conversation(session)
        message = _user_message(session, conversation.id)
        run_repository = RunRepository(session)
        run = run_repository.create(
            conversation_id=conversation.id,
            kind="initial_plan",
            trigger_message_id=message.id,
            base_plan_id=None,
            requirements_snapshot=_requirements(1, "pending"),
            revision_request=None,
        )
        repository = PlanVersionRepository(session)
        plan = repository.create_validated(
            conversation_id=conversation.id,
            run_id=run.id,
            base_plan_id=None,
            plan_schema_version="1.2.0",
            plan={"schema_version": "1.2.0", "plan_id": "placeholder"},
            changed_days=[1],
            change_summary=["生成第一版行程"],
            knowledge_index_version="beijing-photo-spot-v1",
            retrieval_run_ids=["rr-1"],
        )
        assert plan.version == 1
        assert plan.plan_json["plan_id"] == plan.id
        session.flush()

    with factory() as session:
        stored = session.get(PlanVersionModel, plan.id)
        stored.change_summary_json = ["篡改历史版本"]
        with pytest.raises(ImmutableRecordError):
            session.commit()


def test_failed_transaction_does_not_leave_partial_conversation(db):
    _, factory = db
    with pytest.raises(RuntimeError):
        with factory.begin() as session:
            _conversation(session, token_hash="token-rollback")
            raise RuntimeError("simulate failure")

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ConversationModel)) == 0
        assert session.scalar(select(func.count()).select_from(MessageModel)) == 0
        assert session.scalar(select(func.count()).select_from(RunModel)) == 0

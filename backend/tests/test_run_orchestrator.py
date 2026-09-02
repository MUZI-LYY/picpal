"""RunOrchestrator 的首次生成闭环测试。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import pytest

from app.db.base import Base
from app.db.models import ConversationModel, PlanVersionModel, RunModel, RunStageEventModel
from app.db.repositories import AnonymousSessionRepository
from app.db.session import create_sqlite_engine
from app.services.conversation_service import ConversationService
from app.services.map_tool import MockMapTool
from app.services.model_adapter import MockModelAdapter
from app.services.photo_spot_retriever import MockPhotoSpotRetriever
from app.services.planner import Planner
from app.services.run_orchestrator import RunOrchestrator
from app.services.validator import Validator


@pytest.fixture()
def db(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'orchestrator.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _mock_planner() -> Planner:
    return Planner(
        model=MockModelAdapter(),
        map_tool=MockMapTool(),
        retriever=MockPhotoSpotRetriever(),
        validator=Validator(),
    )


def _create_run(factory) -> tuple[str, str]:
    with factory.begin() as session:
        owner = AnonymousSessionRepository(session).create(token_hash="token-a")
        turn = ConversationService(session).create_conversation(
            owner_session_id=owner.id,
            client_message_id="client-1",
            text="第一次去北京，想走经典路线，三天，日期待定，轻松",
        )
        assert turn.active_run is not None
        return turn.active_run.id, turn.conversation.id


def test_initial_run_generates_validated_plan_and_stages(db):
    run_id, conversation_id = _create_run(db)

    session = db()
    try:
        RunOrchestrator(_mock_planner())._execute(session, run_id)
        session.commit()
    finally:
        session.close()

    with db() as session:
        run = session.get(RunModel, run_id)
        assert run.status == "succeeded"
        assert run.result_plan_id is not None
        assert run.finished_at is not None

        plan = session.get(PlanVersionModel, run.result_plan_id)
        assert plan is not None
        assert plan.status == "validated"
        assert plan.conversation_id == conversation_id
        assert plan.plan_json["status"] == "validated"
        assert plan.plan_json["days"]

        stages = list(
            session.scalars(
                select(RunStageEventModel)
                .where(RunStageEventModel.run_id == run_id)
                .order_by(RunStageEventModel.sequence)
            )
        )
        assert len(stages) == 6
        assert all(s.status == "succeeded" for s in stages)

        conversation = session.get(ConversationModel, conversation_id)
        assert conversation.latest_plan_id == plan.id
        assert conversation.active_run_id is None
        assert conversation.status == "completed"


def test_run_ignored_when_not_queued(db):
    run_id, _ = _create_run(db)

    session = db()
    try:
        orchestrator = RunOrchestrator(_mock_planner())
        orchestrator._execute(session, run_id)
        session.commit()
        # 第二次执行：状态已不是 queued，应直接返回，不再重复生成
        orchestrator._execute(session, run_id)
        session.commit()
    finally:
        session.close()

    with db() as session:
        plans = list(session.scalars(select(PlanVersionModel)))
        assert len(plans) == 1

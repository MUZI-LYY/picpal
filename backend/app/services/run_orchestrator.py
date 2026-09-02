"""RunOrchestrator：把 queued Run 真实推进到 succeeded/failed，并写入六阶段进度。"""
from __future__ import annotations

import threading
import time
from datetime import timedelta
from functools import lru_cache
from typing import Optional

from ..core.config import settings
from ..core.errors import AppError
from ..db.repositories import PlanVersionRepository, RunRepository, RunStageEventRepository
from ..db.session import get_session_factory
from ..schemas.conversation import RequirementsSnapshot
from ..schemas.request import LodgingInput, ParsedTripRequest
from .planner import Planner

STAGE_KEYS = (
    "understanding_request",
    "resolving_pois",
    "planning_routes",
    "recommending_lodging",
    "retrieving_photo_spots",
    "validating",
)


def requirements_to_parsed(requirements: RequirementsSnapshot, run_id: str) -> ParsedTripRequest:
    """把已补齐的 RequirementsSnapshot 转成 Planner 需要的 ParsedTripRequest。"""
    start_date = requirements.start_date if requirements.date_status == "specified" else None
    end_date = (
        start_date + timedelta(days=requirements.days - 1)
        if start_date is not None and requirements.days is not None
        else None
    )
    original_text = f"北京{requirements.days}天旅行" if requirements.days else "北京旅行"
    return ParsedTripRequest(
        request_id=f"req:{run_id}",
        original_text=original_text,
        city="北京",
        start_date=start_date,
        end_date=end_date,
        days=requirements.days or 1,
        party_size=requirements.party_size,
        companion_types=list(requirements.companion_types),
        must_include=list(requirements.must_include),
        must_exclude=list(requirements.must_exclude),
        interests=list(requirements.interests),
        photo_preferences=list(requirements.photo_preferences),
        pace=requirements.pace,
        lodging_input=(
            LodgingInput(raw_text=requirements.lodging_text) if requirements.lodging_text else None
        ),
        transport_preferences=list(requirements.transport_preferences),
    )


class RunOrchestrator:
    def __init__(self, planner: Planner):
        self.planner = planner

    def start(self, run_id: str) -> None:
        threading.Thread(target=self._run, args=(run_id,), daemon=True).start()

    def _run(self, run_id: str) -> None:
        session = get_session_factory()()
        try:
            run = None
            for _ in range(20):
                run = RunRepository(session).get(run_id)
                if run is not None:
                    break
                session.rollback()
                time.sleep(0.05)
            if run is None:
                return
            self._execute(session, run_id)
            session.commit()
        except Exception as exc:  # noqa: BLE001 兜底，不向用户泄露堆栈
            session.rollback()
            self._mark_failed(run_id, exc)
        finally:
            session.close()

    def _execute(self, session, run_id: str) -> None:
        runs = RunRepository(session)
        stages = RunStageEventRepository(session)
        run = runs.get(run_id)
        if run is None or run.status != "queued":
            return

        runs.mark_running(run_id)
        stages.seed(run_id, list(STAGE_KEYS))
        session.commit()

        requirements = RequirementsSnapshot.model_validate(run.requirements_snapshot_json)
        parsed = requirements_to_parsed(requirements, run_id)

        previous: dict[str, Optional[str]] = {"key": None}

        def on_stage(key: str) -> None:
            if previous["key"] is not None:
                stages.complete(run_id, previous["key"])
            stages.start(run_id, key)
            runs.set_stage(run_id, key)
            session.commit()
            previous["key"] = key

        plan = self.planner.generate(parsed, stage_callback=on_stage)

        if previous["key"] is not None:
            stages.complete(run_id, previous["key"])

        if plan.status == "validated":
            PlanVersionRepository(session).create_validated(
                conversation_id=run.conversation_id,
                run_id=run_id,
                base_plan_id=run.base_plan_id,
                plan_schema_version=plan.schema_version,
                plan=plan.model_dump(mode="json"),
                changed_days=[day.day_index for day in plan.days],
                change_summary=(
                    ["生成第一版北京行程"] if run.kind == "initial_plan" else ["已按你的要求更新行程"]
                ),
                knowledge_index_version="beijing-photo-spot-v1",
                retrieval_run_ids=[],
            )
        else:
            runs.finish_failed(
                run_id,
                code="validation_failed",
                message="行程没有通过合理性检查，请调整需求后重试",
            )

    def _mark_failed(self, run_id: str, exc: Exception) -> None:
        session = get_session_factory()()
        try:
            runs = RunRepository(session)
            run = runs.get(run_id)
            if run is None:
                return
            if run.current_stage:
                RunStageEventRepository(session).fail(run_id, run.current_stage)
            code = exc.code if isinstance(exc, AppError) else "planning_failed"
            message = exc.message if isinstance(exc, AppError) else "生成失败，请稍后重试"
            runs.finish_failed(run_id, code=code, message=message)
            session.commit()
        finally:
            session.close()


@lru_cache(maxsize=1)
def get_run_orchestrator() -> RunOrchestrator:
    """构建与旧 /trips 相同配置的 Planner，供 RunOrchestrator 使用。"""
    from .amap_tool import AmapMapTool
    from .map_tool import MockMapTool
    from .model_adapter import DeepSeekModelAdapter, MockModelAdapter
    from .photo_spot_retriever import RAGPhotoSpotRetriever
    from .validator import Validator

    model = DeepSeekModelAdapter() if settings.has_real_llm else MockModelAdapter()
    map_tool = AmapMapTool() if settings.map_api_key else MockMapTool()
    planner = Planner(
        model=model,
        map_tool=map_tool,
        retriever=RAGPhotoSpotRetriever(),
        validator=Validator(),
    )
    return RunOrchestrator(planner)

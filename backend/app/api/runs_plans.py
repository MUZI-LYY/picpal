"""Run 与 PlanVersion 查询 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from ..core.errors import error_body
from ..db.repositories import PlanVersionRepository, RunRepository
from ..schemas.conversation import PlanVersionResponse, RunResponse
from .conversations import _plan_version, _run
from .dependencies import get_db_session, require_invited_owner


router = APIRouter(prefix="/api/v1", tags=["Runs"])


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str = Path(min_length=1, max_length=128),
    session: Session = Depends(get_db_session),
    owner=Depends(require_invited_owner),
):
    run = RunRepository(session).get_owned(run_id, owner.id)
    if run is None:
        raise HTTPException(status_code=404, detail=error_body("not_found", "任务不存在"))
    return {"data": _run(run, session)}


@router.get("/plans/{plan_id}", response_model=PlanVersionResponse)
def get_plan(
    plan_id: str = Path(min_length=1, max_length=128),
    session: Session = Depends(get_db_session),
    owner=Depends(require_invited_owner),
):
    plan = PlanVersionRepository(session).get_owned(plan_id, owner.id)
    if plan is None:
        raise HTTPException(status_code=404, detail=error_body("not_found", "行程版本不存在"))
    return {"data": _plan_version(plan)}

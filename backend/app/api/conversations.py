"""正式 Conversation HTTP API。"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.session_security import SessionSigner, SessionTokenError, hash_session_id
from ..db.models import ConversationModel, MessageModel, PlanVersionModel, RunModel
from ..db.repositories import (
    AnonymousSessionRepository,
    ConversationRepository,
    MessageRepository,
    PlanVersionRepository,
    RunStageEventRepository,
)
from ..core.errors import error_body
from ..schemas.conversation import (
    ConversationListResponse,
    ConversationSnapshotResponse,
    ConversationTurnResponse,
    CreateConversationRequest,
    CreateMessageRequest,
)
from ..services.conversation_service import ConversationService, ConversationTurn
from ..services.intent_parser import get_intent_parser
from ..services.run_orchestrator import get_run_orchestrator
from .dependencies import (
    SESSION_COOKIE_NAME,
    get_db_session,
    get_session_signer,
    require_anonymous_owner,
    require_invited_owner,
)


router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])

_STAGES = (
    ("understanding_request", "理解旅行需求"),
    ("resolving_pois", "确认景点位置"),
    ("planning_routes", "规划每日路线"),
    ("recommending_lodging", "评估住宿区域"),
    ("retrieving_photo_spots", "检索出片机位"),
    ("validating", "校验完整行程"),
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _conversation(record: ConversationModel) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "requirements": record.requirements_json,
        "latest_plan_id": record.latest_plan_id,
        "active_run_id": record.active_run_id,
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
    }


def _message(record: MessageModel) -> dict:
    return {
        "id": record.id,
        "conversation_id": record.conversation_id,
        "role": record.role,
        "content_type": record.content_type,
        "text": record.text,
        "structured_content": record.structured_content_json,
        "reply_to_message_id": record.reply_to_message_id,
        "run_id": record.run_id,
        "plan_id": record.plan_id,
        "created_at": _iso(record.created_at),
    }


def _run(record: RunModel | None, session: Session) -> dict | None:
    if record is None:
        return None
    stage_records = RunStageEventRepository(session).list_for(record.id)
    stages_by_key = {s.stage_key: s for s in stage_records}
    error = None
    if record.status == "failed":
        error = {
            "code": record.error_code or "run_failed",
            "message": record.error_message or "旅行计划生成失败",
            "recoverable": True,
        }
    return {
        "id": record.id,
        "conversation_id": record.conversation_id,
        "kind": record.kind,
        "status": record.status,
        "trigger_message_id": record.trigger_message_id,
        "base_plan_id": record.base_plan_id,
        "result_plan_id": record.result_plan_id,
        "current_stage": record.current_stage,
        "stages": [
            {
                "key": key,
                "label": label,
                "status": stages_by_key[key].status if key in stages_by_key else "waiting",
                "started_at": _iso(stages_by_key[key].started_at) if key in stages_by_key else None,
                "completed_at": _iso(stages_by_key[key].completed_at) if key in stages_by_key else None,
            }
            for key, label in _STAGES
        ],
        "error": error,
        "created_at": _iso(record.created_at),
        "started_at": _iso(record.started_at),
        "finished_at": _iso(record.finished_at),
    }


def _plan_version(record: PlanVersionModel) -> dict:
    plan = dict(record.plan_json)
    plan["plan_id"] = record.id
    return {
        "id": record.id,
        "conversation_id": record.conversation_id,
        "run_id": record.run_id,
        "version": record.version,
        "base_plan_id": record.base_plan_id,
        "status": record.status,
        "changed_days": record.changed_days_json,
        "change_summary": record.change_summary_json,
        "plan": plan,
        "retrieval_run_ids": record.retrieval_run_ids_json,
        "knowledge_index_version": record.knowledge_index_version,
        "created_at": _iso(record.created_at),
    }


def _latest_plan(conversation: ConversationModel, session: Session) -> dict | None:
    if not conversation.latest_plan_id:
        return None
    record = PlanVersionRepository(session).get(conversation.latest_plan_id)
    return _plan_version(record) if record else None


def _turn(turn: ConversationTurn, session: Session) -> dict:
    return {
        "data": {
            "conversation": _conversation(turn.conversation),
            "accepted_message": _message(turn.accepted_message),
            "assistant_messages": [_message(item) for item in turn.assistant_messages],
            "active_run": _run(turn.active_run, session),
            "latest_plan": _latest_plan(turn.conversation, session),
        }
    }


def _owner_for_create(
    request: Request,
    response: Response,
    session: Session,
    signer: SessionSigner,
):
    signed_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    session_id: str | None = None
    if signed_cookie:
        try:
            session_id = signer.verify(signed_cookie)
        except SessionTokenError:
            session_id = None
    if session_id is None:
        session_id, signed_cookie = signer.issue()
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=signed_cookie,
            max_age=signer.max_age_seconds,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="strict",
            path="/",
        )
    return AnonymousSessionRepository(session).create(
        token_hash=hash_session_id(session_id)
    )


@router.post("", status_code=201, response_model=ConversationTurnResponse)
def create_conversation(
    body: CreateConversationRequest,
    request: Request,
    response: Response,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: Session = Depends(get_db_session),
    signer: SessionSigner = Depends(get_session_signer),
):
    del idempotency_key
    owner = _owner_for_create(request, response, session, signer)
    if not owner.invited:
        raise HTTPException(
            status_code=401,
            detail=error_body("invite_required", "需要邀请码才能使用"),
        )
    conversations = ConversationRepository(session)
    existing = conversations.get_by_owner_client_message(
        owner.id, body.client_message_id
    )
    service = ConversationService(session, intent_parser=get_intent_parser())
    if existing is None:
        turn = service.create_conversation(
            owner_session_id=owner.id,
            client_message_id=body.client_message_id,
            text=body.text,
        )
    else:
        turn = service.create_message(
            owner_session_id=owner.id,
            conversation_id=existing.id,
            client_message_id=body.client_message_id,
            text=body.text,
            reply_to_message_id=None,
            structured_answer=None,
            base_plan_id=None,
        )
    response.headers["Location"] = f"/api/v1/conversations/{turn.conversation.id}"
    if turn.active_run is not None:
        get_run_orchestrator().start(turn.active_run.id)
    return _turn(turn, session)


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=2048),
    session: Session = Depends(get_db_session),
    owner=Depends(require_invited_owner),
):
    records, next_cursor = ConversationRepository(session).list_owned(
        owner.id, limit=limit, cursor=cursor
    )
    messages = MessageRepository(session)
    return {
        "data": [
            {
                "id": item.id,
                "title": item.title,
                "preview": messages.latest_user_preview(item.id),
                "status": item.status,
                "latest_plan_id": item.latest_plan_id,
                "updated_at": _iso(item.updated_at),
            }
            for item in records
        ],
        "meta": {
            "has_next": next_cursor is not None,
            "next_cursor": next_cursor,
        },
    }


@router.get("/{conversation_id}", response_model=ConversationSnapshotResponse)
def get_conversation(
    conversation_id: str = Path(min_length=1, max_length=128),
    session: Session = Depends(get_db_session),
    owner=Depends(require_invited_owner),
):
    conversation = ConversationRepository(session).get_owned(
        conversation_id, owner.id
    )
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail=error_body("not_found", "对话不存在"),
        )
    messages, has_more, before_cursor = MessageRepository(session).list_recent(
        conversation.id, limit=50
    )
    active_run = (
        session.get(RunModel, conversation.active_run_id)
        if conversation.active_run_id
        else None
    )
    return {
        "data": {
            "conversation": _conversation(conversation),
            "messages": [_message(item) for item in messages],
            "message_page": {
                "has_more": has_more,
                "before_cursor": before_cursor,
            },
            "active_run": _run(active_run, session),
            "latest_plan": _latest_plan(conversation, session),
        }
    }


@router.post(
    "/{conversation_id}/messages",
    status_code=201,
    response_model=ConversationTurnResponse,
)
def create_conversation_message(
    body: CreateMessageRequest,
    conversation_id: str = Path(min_length=1, max_length=128),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: Session = Depends(get_db_session),
    owner=Depends(require_invited_owner),
):
    del idempotency_key
    answer = (
        body.structured_answer.model_dump(mode="json")
        if body.structured_answer is not None
        else None
    )
    turn = ConversationService(session, intent_parser=get_intent_parser()).create_message(
        owner_session_id=owner.id,
        conversation_id=conversation_id,
        client_message_id=body.client_message_id,
        text=body.text,
        reply_to_message_id=body.reply_to_message_id,
        structured_answer=answer,
        base_plan_id=body.base_plan_id,
    )
    if turn.active_run is not None:
        get_run_orchestrator().start(turn.active_run.id)
    return _turn(turn, session)

"""内测邀请码校验接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import error_body
from ..core.session_security import SessionSigner, SessionTokenError, hash_session_id
from ..db.repositories import AnonymousSessionRepository
from .dependencies import SESSION_COOKIE_NAME, get_db_session, get_session_signer


router = APIRouter(prefix="/api/v1/invites", tags=["Invites"])


class VerifyInviteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


def _owner(request: Request, response: Response, session: Session, signer: SessionSigner):
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
    return AnonymousSessionRepository(session).create(token_hash=hash_session_id(session_id))


@router.post("/verify")
def verify_invite(
    body: VerifyInviteRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
    signer: SessionSigner = Depends(get_session_signer),
):
    if not settings.valid_invite_codes:
        raise HTTPException(
            status_code=503,
            detail=error_body("service_unavailable", "邀请码服务尚未配置"),
        )
    if body.code not in settings.valid_invite_codes:
        raise HTTPException(
            status_code=401,
            detail=error_body("invalid_invite", "邀请码无效"),
        )
    owner = _owner(request, response, session, signer)
    owner.invited = True
    session.flush()
    return {"data": {"invited": True}}

"""正式 API 的数据库与匿名会话依赖。"""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import error_body
from ..core.session_security import SessionSigner, SessionTokenError, hash_session_id
from ..db.models import AnonymousSessionModel
from ..db.repositories import AnonymousSessionRepository
from ..db.session import get_session_factory


SESSION_COOKIE_NAME = "trip_session"


def get_db_session() -> Iterator[Session]:
    with get_session_factory().begin() as session:
        yield session


@lru_cache(maxsize=1)
def get_session_signer() -> SessionSigner:
    if not settings.session_signing_secret:
        raise HTTPException(
            status_code=503,
            detail=error_body("service_unavailable", "匿名会话服务尚未配置"),
        )
    return SessionSigner(settings.session_signing_secret)


def require_anonymous_owner(
    trip_session: str | None = Cookie(default=None),
    session: Session = Depends(get_db_session),
    signer: SessionSigner = Depends(get_session_signer),
) -> AnonymousSessionModel:
    if not trip_session:
        raise HTTPException(
            status_code=401,
            detail=error_body("session_required", "需要匿名会话"),
        )
    try:
        session_id = signer.verify(trip_session)
    except SessionTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=error_body(exc.code, "匿名会话无效，请重新开始"),
        ) from exc
    return AnonymousSessionRepository(session).create(
        token_hash=hash_session_id(session_id)
    )


def require_invited_owner(
    owner: AnonymousSessionModel = Depends(require_anonymous_owner),
) -> AnonymousSessionModel:
    if not owner.invited:
        raise HTTPException(
            status_code=401,
            detail=error_body("invite_required", "需要邀请码才能使用"),
        )
    return owner

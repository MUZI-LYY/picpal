"""内测邀请码接口测试。"""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db_session, get_session_signer
from app.core.session_security import SessionSigner
from app.db.base import Base
from app.db.session import create_sqlite_engine
from app.main import app

SIGNING_SECRET = "invite-test-signing-secret-with-at-least-32-bytes"


def _verify(client: TestClient, code: str):
    return client.post("/api/v1/invites/verify", json={"code": code})


def test_invalid_invite_code_is_rejected(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'invite.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    signer = SessionSigner(SIGNING_SECRET)

    def override_db():
        with factory.begin() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_session_signer] = lambda: signer
    try:
        with TestClient(app, base_url="https://testserver") as client:
            response = _verify(client, "wrong-code")
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "invalid_invite"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_valid_invite_unlocks_conversation(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'invite.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    signer = SessionSigner(SIGNING_SECRET)

    def override_db():
        with factory.begin() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_session_signer] = lambda: signer
    try:
        with TestClient(app, base_url="https://testserver") as client:
            assert _verify(client, "test-invite").status_code == 200

            created = client.post(
                "/api/v1/conversations",
                headers={"Idempotency-Key": str(uuid4())},
                json={"client_message_id": "c1", "text": "北京三天，日期待定，轻松"},
            )
            assert created.status_code == 201
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

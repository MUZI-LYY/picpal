"""正式 Conversation API：创建对话与历史列表。"""
from __future__ import annotations

import copy
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db_session, get_session_signer
from app.core.session_security import SessionSigner, hash_session_id
from app.db.base import Base
from app.db.models import AnonymousSessionModel
from app.db.session import create_sqlite_engine
from app.main import app


BACKEND_DIR = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((BACKEND_DIR / "contracts" / "openapi-v1.yaml").read_text("utf-8"))
SIGNING_SECRET = "api-test-signing-secret-with-at-least-32-bytes"


def _validate(schema_name: str, payload: dict) -> None:
    root = copy.deepcopy(SPEC)
    root["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    root["$ref"] = f"#/components/schemas/{schema_name}"
    Draft202012Validator(root, format_checker=FormatChecker()).validate(payload)


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _create(client: TestClient, text: str, client_message_id: str = "client-1"):
    return client.post(
        "/api/v1/conversations",
        headers=_headers(),
        json={"client_message_id": client_message_id, "text": text},
    )


def _invite(client: TestClient, code: str = "test-invite"):
    return client.post("/api/v1/invites/verify", json={"code": code})


def test_create_conversation_sets_secure_cookie_and_matches_contract(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'api.db'}")
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
            invite_response = _invite(client)
            assert invite_response.status_code == 200
            set_cookie = invite_response.headers["set-cookie"].lower()
            assert "trip_session=" in set_cookie
            assert "httponly" in set_cookie
            assert "secure" in set_cookie
            assert "samesite=strict" in set_cookie
            assert "path=/" in set_cookie

            response = _create(client, "第一次去北京，想走经典路线，每天别太赶")
            assert response.status_code == 201
            payload = response.json()
            _validate("ConversationTurnResponse", payload)
            conversation_id = payload["data"]["conversation"]["id"]
            assert response.headers["location"] == f"/api/v1/conversations/{conversation_id}"

            signed_cookie = client.cookies.get("trip_session")
            raw_session_id = signer.verify(signed_cookie)
            with factory() as session:
                stored = session.scalar(select(AnonymousSessionModel))
                assert stored.token_hash == hash_session_id(raw_session_id)
                assert raw_session_id not in stored.token_hash
                assert stored.invited is True
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_list_requires_valid_cookie_and_isolates_anonymous_owners(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'isolation.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    signer = SessionSigner(SIGNING_SECRET)

    def override_db():
        with factory.begin() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_session_signer] = lambda: signer
    try:
        with (
            TestClient(app, base_url="https://testserver") as owner_a,
            TestClient(app, base_url="https://testserver") as owner_b,
        ):
            assert _invite(owner_a).status_code == 200
            assert _invite(owner_b).status_code == 200
            created_a = _create(owner_a, "北京三天，日期待定", "owner-a-message")
            created_b = _create(owner_b, "北京两天，日期待定", "owner-b-message")
            assert created_a.status_code == created_b.status_code == 201

            listed = owner_a.get("/api/v1/conversations?limit=20")
            assert listed.status_code == 200
            payload = listed.json()
            _validate("ConversationListResponse", payload)
            assert [item["id"] for item in payload["data"]] == [
                created_a.json()["data"]["conversation"]["id"]
            ]
            assert payload["data"][0]["preview"] == "北京三天，日期待定"

        with TestClient(app, base_url="https://testserver") as anonymous:
            missing = anonymous.get("/api/v1/conversations")
            assert missing.status_code == 401
            assert missing.json()["error"]["code"] == "session_required"

            _, valid_token = signer.issue()
            payload_part, signature = valid_token.split(".")
            replacement = "A" if signature[0] != "A" else "B"
            tampered = f"{payload_part}.{replacement}{signature[1:]}"
            invalid = anonymous.get(
                "/api/v1/conversations",
                headers={"cookie": f"trip_session={tampered}"},
            )
            assert invalid.status_code == 401
            assert invalid.json()["error"]["code"] == "invalid_session"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_restore_and_continue_conversation_matches_contract(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'conversation-turns.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    signer = SessionSigner(SIGNING_SECRET)

    def override_db():
        with factory.begin() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_session_signer] = lambda: signer
    try:
        with (
            TestClient(app, base_url="https://testserver") as owner,
            TestClient(app, base_url="https://testserver") as stranger,
        ):
            assert _invite(owner).status_code == 200
            created = _create(owner, "第一次去北京，想拍经典机位")
            assert created.status_code == 201
            first_turn = created.json()["data"]
            conversation_id = first_turn["conversation"]["id"]
            days_question = first_turn["assistant_messages"][0]

            restored = owner.get(f"/api/v1/conversations/{conversation_id}")
            assert restored.status_code == 200
            _validate("ConversationSnapshotResponse", restored.json())
            assert len(restored.json()["data"]["messages"]) == 2
            assert restored.json()["data"]["active_run"] is None

            mismatched = owner.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=_headers(),
                json={
                    "client_message_id": "client-bad-slot",
                    "text": "日期待定",
                    "reply_to_message_id": days_question["id"],
                    "structured_answer": {"slot": "start_date", "value": "pending"},
                    "base_plan_id": None,
                },
            )
            assert mismatched.status_code == 422
            assert mismatched.json()["error"]["code"] == "invalid_slot_value"

            answered_days = owner.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=_headers(),
                json={
                    "client_message_id": "client-days",
                    "text": "3 天",
                    "reply_to_message_id": days_question["id"],
                    "structured_answer": {"slot": "days", "value": 3},
                    "base_plan_id": None,
                },
            )
            assert answered_days.status_code == 201
            _validate("ConversationTurnResponse", answered_days.json())
            date_question = answered_days.json()["data"]["assistant_messages"][0]
            assert date_question["structured_content"]["slot"] == "start_date"

            started = owner.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=_headers(),
                json={
                    "client_message_id": "client-date",
                    "text": "日期待定",
                    "reply_to_message_id": date_question["id"],
                    "structured_answer": {"slot": "start_date", "value": "pending"},
                    "base_plan_id": None,
                },
            )
            assert started.status_code == 201
            _validate("ConversationTurnResponse", started.json())
            assert started.json()["data"]["active_run"] is None
            pace_question = started.json()["data"]["assistant_messages"][0]
            assert pace_question["structured_content"]["slot"] == "pace"

            answered_pace = owner.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                headers=_headers(),
                json={
                    "client_message_id": "client-pace",
                    "text": "轻松",
                    "reply_to_message_id": pace_question["id"],
                    "structured_answer": {"slot": "pace", "value": "轻松"},
                    "base_plan_id": None,
                },
            )
            assert answered_pace.status_code == 201
            _validate("ConversationTurnResponse", answered_pace.json())
            assert answered_pace.json()["data"]["active_run"]["status"] == "queued"

            restored_running = owner.get(f"/api/v1/conversations/{conversation_id}")
            assert restored_running.status_code == 200
            _validate("ConversationSnapshotResponse", restored_running.json())
            assert len(restored_running.json()["data"]["messages"]) == 8
            assert restored_running.json()["data"]["active_run"]["status"] == "queued"

            assert _invite(stranger).status_code == 200
            assert _create(stranger, "北京两天，日期待定", "stranger-message").status_code == 201
            hidden = stranger.get(f"/api/v1/conversations/{conversation_id}")
            assert hidden.status_code == 404
            assert hidden.json()["error"]["code"] == "not_found"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

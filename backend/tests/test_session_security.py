"""匿名会话 Cookie 签名与凭证存储安全测试。"""
from __future__ import annotations

import pytest

from app.core.session_security import (
    SessionSigner,
    SessionTokenError,
    hash_session_id,
)


SECRET = "test-session-secret-with-at-least-32-bytes"


def test_issued_token_round_trips_and_database_value_is_one_way_hash():
    signer = SessionSigner(SECRET, max_age_seconds=3600)
    session_id, token = signer.issue(now=1_000)

    assert signer.verify(token, now=1_100) == session_id
    assert len(session_id) >= 32
    assert hash_session_id(session_id) != session_id
    assert hash_session_id(session_id) == hash_session_id(session_id)
    assert len(hash_session_id(session_id)) == 64


def test_tampered_signature_is_rejected_without_exposing_details():
    signer = SessionSigner(SECRET)
    _, token = signer.issue(now=1_000)
    payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered = f"{payload}.{replacement}{signature[1:]}"

    with pytest.raises(SessionTokenError) as error:
        signer.verify(tampered, now=1_001)

    assert error.value.code == "invalid_session"
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("token", ["", "missing-dot", "a.b.c", "!.!"])
def test_malformed_token_is_rejected(token):
    signer = SessionSigner(SECRET)

    with pytest.raises(SessionTokenError) as error:
        signer.verify(token, now=1_000)

    assert error.value.code == "invalid_session"


def test_expired_and_future_dated_tokens_are_rejected():
    signer = SessionSigner(SECRET, max_age_seconds=60, clock_skew_seconds=5)
    _, token = signer.issue(now=1_000)

    with pytest.raises(SessionTokenError) as expired:
        signer.verify(token, now=1_061)
    assert expired.value.code == "session_expired"

    with pytest.raises(SessionTokenError) as future:
        signer.verify(token, now=994)
    assert future.value.code == "invalid_session"


def test_short_signing_secret_is_rejected():
    with pytest.raises(ValueError, match="至少 32"):
        SessionSigner("too-short")

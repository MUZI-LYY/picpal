"""匿名会话 Cookie 的 HMAC 签名、校验与数据库哈希。"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


class SessionTokenError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def hash_session_id(session_id: str) -> str:
    """数据库只保存不可逆摘要，不保存浏览器持有的原始凭证。"""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


class SessionSigner:
    VERSION = 1

    def __init__(
        self,
        secret: str,
        *,
        max_age_seconds: int = 180 * 24 * 60 * 60,
        clock_skew_seconds: int = 30,
    ):
        secret_bytes = secret.encode("utf-8")
        if len(secret_bytes) < 32:
            raise ValueError("SESSION_SIGNING_SECRET 至少 32 字节")
        if max_age_seconds <= 0 or clock_skew_seconds < 0:
            raise ValueError("会话有效期配置无效")
        self._secret = secret_bytes
        self.max_age_seconds = max_age_seconds
        self.clock_skew_seconds = clock_skew_seconds

    def issue(self, *, now: int | None = None) -> tuple[str, str]:
        issued_at = int(time.time()) if now is None else int(now)
        session_id = secrets.token_urlsafe(32)
        payload = {"iat": issued_at, "sid": session_id, "v": self.VERSION}
        payload_bytes = json.dumps(
            payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        return session_id, f"{_encode(payload_bytes)}.{_encode(signature)}"

    def verify(self, token: str, *, now: int | None = None) -> str:
        try:
            payload_part, signature_part = token.split(".")
            payload_bytes = _decode(payload_part)
            supplied_signature = _decode(signature_part)
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise SessionTokenError("invalid_session", "匿名会话凭证无效") from exc

        expected_signature = hmac.new(
            self._secret, payload_bytes, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise SessionTokenError("invalid_session", "匿名会话凭证无效")

        payload = self._parse_payload(payload_bytes)
        checked_at = int(time.time()) if now is None else int(now)
        issued_at = payload["iat"]
        if issued_at - checked_at > self.clock_skew_seconds:
            raise SessionTokenError("invalid_session", "匿名会话凭证无效")
        if checked_at - issued_at > self.max_age_seconds:
            raise SessionTokenError("session_expired", "匿名会话已过期")
        return payload["sid"]

    @classmethod
    def _parse_payload(cls, payload_bytes: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SessionTokenError("invalid_session", "匿名会话凭证无效") from exc
        if not isinstance(payload, dict) or set(payload) != {"iat", "sid", "v"}:
            raise SessionTokenError("invalid_session", "匿名会话凭证无效")
        if payload.get("v") != cls.VERSION:
            raise SessionTokenError("invalid_session", "匿名会话凭证无效")
        issued_at = payload.get("iat")
        session_id = payload.get("sid")
        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            raise SessionTokenError("invalid_session", "匿名会话凭证无效")
        if not isinstance(session_id, str) or not 32 <= len(session_id) <= 256:
            raise SessionTokenError("invalid_session", "匿名会话凭证无效")
        return payload

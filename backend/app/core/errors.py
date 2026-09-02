"""统一错误结构与异常。"""
from __future__ import annotations

import uuid
from typing import Any


class AppError(Exception):
    """业务异常，携带统一错误码。"""

    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def error_body(
    code: str,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """正式 API 错误结构；不包含堆栈、SQL 或凭证。"""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id or f"api_req_{uuid.uuid4().hex}",
        }
    }

"""Repository 层的稳定业务错误。"""
from __future__ import annotations


class RepositoryError(Exception):
    """数据层可识别错误基类。"""


class IdempotencyConflict(RepositoryError):
    """同一个客户端消息 ID 被用于不同请求。"""


class ActiveRunConflict(RepositoryError):
    """同一 Conversation 已存在 queued/running Run。"""


class ImmutableRecordError(RepositoryError):
    """尝试修改或删除不可变的 PlanVersion。"""

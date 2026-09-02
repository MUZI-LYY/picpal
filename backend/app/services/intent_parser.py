"""LLM 意图解析器：把用户自由文本解析成需求字段，失败返回 None 由规则兜底。"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..core.config import settings
from ..schemas.conversation import RequirementsSnapshot
from .llm_client import LLMClient

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "parse_intent.md"


class IntentFields(BaseModel):
    """LLM 返回的意图字段，全部可空；None 表示本轮未提及，不覆盖已有值。"""

    model_config = ConfigDict(extra="forbid")

    days: int | None = Field(default=None, ge=1, le=5)
    date_status: Literal["specified", "pending", "unknown"] | None = None
    start_date: date | None = None
    party_size: int | None = Field(default=None, ge=1)
    companion_types: list[str] | None = None
    must_include: list[str] | None = None
    must_exclude: list[str] | None = None
    interests: list[str] | None = None
    photo_preferences: list[str] | None = None
    pace: Literal["轻松", "适中", "紧凑"] | None = None
    lodging_text: str | None = None
    transport_preferences: list[str] | None = None


class IntentParser:
    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
        self.system = PROMPT_PATH.read_text(encoding="utf-8")

    def parse(self, text: str, current: RequirementsSnapshot) -> Optional[IntentFields]:
        """解析成功返回 IntentFields；任何失败返回 None，交由规则兜底。"""
        user = json.dumps(
            {
                "text": text,
                "today": date.today().isoformat(),
                "current": current.model_dump(mode="json", exclude={"missing_slots"}),
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.complete_json(self.system, user)
            return IntentFields.model_validate(data)
        except Exception:  # noqa: BLE001 意图解析是增强能力，任何失败都回退规则
            return None


@lru_cache(maxsize=1)
def get_intent_parser() -> Optional[IntentParser]:
    """无真实 LLM 时返回 None（纯规则）；有则返回可复用的解析器。"""
    if not settings.has_real_llm:
        return None
    return IntentParser()

"""LLM 意图解析器与 RequirementCollector 合并逻辑的测试。"""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.conversation import RequirementsSnapshot
from app.services.intent_parser import IntentFields, IntentParser
from app.services.requirement_collector import RequirementCollector


class _FakeClient:
    """固定返回给定 JSON 的假 LLM 客户端。"""

    def __init__(self, result: dict | None = None):
        self.result = result
        self.calls = 0

    def complete_json(self, system: str, user: str) -> dict:
        self.calls += 1
        if self.result is None:
            raise RuntimeError("network down")
        return self.result


def test_intent_parser_parses_valid_json():
    client = _FakeClient(
        {
            "days": 5,
            "date_status": "specified",
            "start_date": "2026-08-30",
            "party_size": 2,
            "companion_types": ["朋友"],
            "must_include": ["故宫"],
            "must_exclude": [],
            "interests": ["经典景点"],
            "photo_preferences": [],
            "pace": "轻松",
            "lodging_text": None,
            "transport_preferences": [],
        }
    )
    parser = IntentParser(client=client)
    current = RequirementsSnapshot()
    result = parser.parse("双人5天游", current)

    assert result is not None
    assert result.days == 5
    assert result.start_date == date(2026, 8, 30)
    assert result.party_size == 2


def test_intent_parser_returns_none_on_failure():
    parser = IntentParser(client=_FakeClient(None))
    assert parser.parse("随便说点", RequirementsSnapshot()) is None


def _merge(days, date_status, start_date, party_size):
    req = RequirementsSnapshot()
    req.days = days
    req.date_status = date_status
    req.start_date = start_date
    req.party_size = party_size
    return req


def test_collector_merges_llm_intent_over_rules():
    # 规则识别不到"8.30"点号日期，LLM 补上。
    parser = IntentParser(
        client=_FakeClient(
            {
                "days": 3,
                "date_status": "specified",
                "start_date": "2026-08-30",
                "party_size": None,
                "companion_types": None,
                "must_include": None,
                "must_exclude": None,
                "interests": None,
                "photo_preferences": None,
                "pace": None,
                "lodging_text": None,
                "transport_preferences": None,
            }
        )
    )
    collector = RequirementCollector(intent_parser=parser)
    result = collector.collect("8.30 三天")

    assert result.requirements.days == 3
    assert result.requirements.date_status == "specified"
    assert result.requirements.start_date == date(2026, 8, 30)


def test_collector_falls_back_to_rules_when_llm_fails():
    # LLM 失败时，规则仍能识别"三天"。
    collector = RequirementCollector(intent_parser=IntentParser(client=_FakeClient(None)))
    result = collector.collect("北京玩三天，想去故宫")

    assert result.requirements.days == 3
    assert result.requirements.must_include == ["故宫"]


def test_structured_answer_not_overridden_by_llm():
    # 结构化按钮回答（3 天）优先级最高，LLM 不能覆盖。
    parser = IntentParser(
        client=_FakeClient(
            {
                "days": 5,
                "date_status": None,
                "start_date": None,
                "party_size": None,
                "companion_types": None,
                "must_include": None,
                "must_exclude": None,
                "interests": None,
                "photo_preferences": None,
                "pace": None,
                "lodging_text": None,
                "transport_preferences": None,
            }
        )
    )
    collector = RequirementCollector(intent_parser=parser)
    result = collector.collect(
        "3 天",
        structured_answer={"slot": "days", "value": 3},
    )

    assert result.requirements.days == 3

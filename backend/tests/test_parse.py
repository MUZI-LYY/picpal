"""需求解析（Mock）单元测试。"""
from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.services.model_adapter import DeepSeekModelAdapter, MockModelAdapter

adapter = MockModelAdapter()


def test_parse_days_from_text() -> None:
    p = adapter.parse_request("中秋去北京玩三天", {})
    assert p.days == 3
    assert p.city == "北京"


def test_parse_original_text_preserved() -> None:
    text = "中秋去北京玩三天，和朋友一起，想去故宫、天坛"
    p = adapter.parse_request(text, {})
    assert p.original_text == text


def test_parse_must_include_extracted() -> None:
    p = adapter.parse_request("想去故宫、天坛，多拍照", {})
    assert "故宫" in p.must_include or "故宫博物院" in p.must_include


def test_parse_must_exclude_extracted_and_not_included() -> None:
    p = adapter.parse_request("北京两天，想去天坛，但不去故宫", {})
    assert "故宫" in p.must_exclude or "故宫博物院" in p.must_exclude
    assert "故宫" not in p.must_include
    assert "故宫博物院" not in p.must_include


def test_real_adapter_normalization_gives_exclusion_priority() -> None:
    adapter = DeepSeekModelAdapter(client=object())  # type: ignore[arg-type]
    normalized = adapter._normalize_request(
        {
            "days": 2,
            "must_include": ["故宫", "天坛"],
            "must_exclude": ["故宫博物院"],
        },
        "北京两天",
        {},
    )
    assert normalized["must_include"] == ["天坛"]
    assert normalized["must_exclude"] == ["故宫博物院"]


def test_parse_dates() -> None:
    p = adapter.parse_request("2026-10-01 去北京玩两天", {})
    assert p.start_date is not None
    assert p.end_date is not None
    assert (p.end_date - p.start_date).days == 1


def test_parse_pace_and_preferences() -> None:
    p = adapter.parse_request("轻松一点，喜欢胡同和夜景，少走路", {})
    assert p.pace == "轻松"
    assert "胡同" in p.interests
    assert "少走路" in p.transport_preferences


def test_parse_optional_lodging_from_natural_language() -> None:
    p = adapter.parse_request("北京两天，住在前门，想去故宫", {})
    assert p.lodging_input is not None
    assert p.lodging_input.raw_text == "前门"


def test_parse_does_not_invent_lodging() -> None:
    p = adapter.parse_request("北京两天，想去故宫", {})
    assert p.lodging_input is None


def test_parse_unsupported_city_raises() -> None:
    with pytest.raises(AppError) as e:
        adapter.parse_request("去上海玩三天", {})
    assert e.value.code == "parse_failed"


def test_parse_days_fallback_to_hints() -> None:
    p = adapter.parse_request("去北京玩", {"days": 2})
    assert p.days == 2

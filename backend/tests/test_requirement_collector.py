"""多轮需求补齐的行为测试。"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.requirement_collector import (
    RequirementCollectionError,
    RequirementCollector,
)


@pytest.fixture()
def collector() -> RequirementCollector:
    return RequirementCollector()


def test_missing_days_is_not_defaulted_and_days_is_asked_first(collector):
    result = collector.collect("第一次去北京，想走经典路线，每天别太赶")

    assert result.requirements.days is None
    assert result.requirements.date_status == "unknown"
    assert result.requirements.pace == "轻松"
    assert result.requirements.missing_slots == ["days", "start_date"]
    assert result.ready is False
    assert result.clarification.model_dump() == {
        "kind": "clarification",
        "slot": "days",
        "control": "single_select",
        "options": [
            {"label": "1 天", "value": 1},
            {"label": "2 天", "value": 2},
            {"label": "3 天", "value": 3},
            {"label": "4 天", "value": 4},
            {"label": "5 天", "value": 5},
        ],
        "allow_pending": False,
    }


def test_known_days_with_unknown_date_asks_date_or_pending(collector):
    result = collector.collect("北京玩三天，想去故宫")

    assert result.requirements.days == 3
    assert result.requirements.must_include == ["故宫"]
    assert result.requirements.missing_slots == ["start_date", "pace"]
    assert result.clarification.model_dump() == {
        "kind": "clarification",
        "slot": "start_date",
        "control": "date_or_pending",
        "options": [],
        "allow_pending": True,
    }


def test_structured_days_answer_merges_with_existing_requirements(collector):
    initial = collector.collect("想走经典路线，每天别太赶")
    answered = collector.collect(
        "3 天",
        current=initial.requirements,
        structured_answer={"slot": "days", "value": 3},
    )

    assert answered.requirements.days == 3
    assert answered.requirements.pace == "轻松"
    assert answered.requirements.missing_slots == ["start_date"]
    assert answered.clarification.slot == "start_date"


def test_structured_answer_is_authoritative_when_display_text_disagrees(collector):
    initial = collector.collect("北京玩三天")
    answered = collector.collect(
        "日期待定",
        current=initial.requirements,
        structured_answer={"slot": "start_date", "value": "2026-10-01"},
    )

    assert answered.requirements.date_status == "specified"
    assert answered.requirements.start_date == date(2026, 10, 1)


@pytest.mark.parametrize(
    ("value", "expected_status", "expected_date"),
    [
        ("pending", "pending", None),
        ("2026-10-01", "specified", date(2026, 10, 1)),
    ],
)
def test_date_answer_completes_minimum_requirements(
    collector, value, expected_status, expected_date
):
    with_days = collector.collect("北京玩三天，轻松")
    completed = collector.collect(
        "日期待定" if value == "pending" else value,
        current=with_days.requirements,
        structured_answer={"slot": "start_date", "value": value},
    )

    assert completed.requirements.date_status == expected_status
    assert completed.requirements.start_date == expected_date
    assert completed.requirements.missing_slots == []
    assert completed.ready is True
    assert completed.clarification is None


def test_full_natural_language_request_can_be_ready_without_clarification(collector):
    result = collector.collect("2026年10月1日去北京玩两天，情侣出行，想拍夜景，轻松")

    assert result.ready is True
    assert result.requirements.days == 2
    assert result.requirements.date_status == "specified"
    assert result.requirements.start_date == date(2026, 10, 1)
    assert result.requirements.companion_types == ["情侣"]
    assert result.requirements.photo_preferences == ["城市夜景"]
    assert result.requirements.pace == "轻松"


def test_natural_language_pending_date_is_an_explicit_decision(collector):
    result = collector.collect("北京两天，轻松，具体日期还没定")

    assert result.ready is True
    assert result.requirements.date_status == "pending"
    assert result.requirements.start_date is None
    assert result.requirements.missing_slots == []


def test_pace_is_asked_after_days_and_date(collector):
    with_days = collector.collect("北京玩三天")
    result = collector.collect(
        "日期待定",
        current=with_days.requirements,
        structured_answer={"slot": "start_date", "value": "pending"},
    )

    assert result.requirements.days == 3
    assert result.requirements.date_status == "pending"
    assert result.requirements.missing_slots == ["pace"]
    assert result.clarification.slot == "pace"
    assert result.clarification.model_dump() == {
        "kind": "clarification",
        "slot": "pace",
        "control": "single_select",
        "options": [
            {"label": "休闲慢游", "value": "轻松"},
            {"label": "平衡型", "value": "适中"},
            {"label": "特种兵型", "value": "紧凑"},
        ],
        "allow_pending": False,
    }


def test_pace_answer_completes_requirements(collector):
    with_days = collector.collect("北京玩三天")
    after_date = collector.collect(
        "日期待定",
        current=with_days.requirements,
        structured_answer={"slot": "start_date", "value": "pending"},
    )
    completed = collector.collect(
        "轻松",
        current=after_date.requirements,
        structured_answer={"slot": "pace", "value": "轻松"},
    )

    assert completed.requirements.pace == "轻松"
    assert completed.requirements.missing_slots == []
    assert completed.ready is True
    assert completed.clarification is None


def test_reusing_an_already_answered_structured_slot_is_rejected(collector):
    completed_days = collector.collect("北京三天")

    with pytest.raises(RequirementCollectionError) as error:
        collector.collect(
            "2 天",
            current=completed_days.requirements,
            structured_answer={"slot": "days", "value": 2},
        )

    assert error.value.code == "clarification_already_answered"


def test_other_city_is_rejected_with_stable_error_code(collector):
    with pytest.raises(RequirementCollectionError) as error:
        collector.collect("去上海玩三天，日期待定")

    assert error.value.code == "unsupported_city"

"""允许关键槽位缺失的多轮旅行需求收集器。"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ..core.errors import AppError
from ..schemas.conversation import (
    ClarificationContent,
    ClarificationOption,
    DaysAnswer,
    RequirementCollectionResult,
    RequirementsSnapshot,
    PaceAnswer,
    StartDateAnswer,
    StructuredAnswer,
)
from .intent_parser import IntentFields
from .model_adapter import (
    _extract_attractions,
    _extract_excluded_attractions,
    _extract_lodging_text,
    _remove_excluded_attractions,
    check_city,
)


_ANSWER_ADAPTER = TypeAdapter(StructuredAnswer)
_DAYS = {
    "一天": 1,
    "一日": 1,
    "两天": 2,
    "两日": 2,
    "二天": 2,
    "二日": 2,
    "三天": 3,
    "三日": 3,
    "四天": 4,
    "四日": 4,
    "五天": 5,
    "五日": 5,
}
_PEOPLE = {
    "一人": 1,
    "单人": 1,
    "两人": 2,
    "双人": 2,
    "二人": 2,
    "三人": 3,
    "四人": 4,
    "五人": 5,
    "六人": 6,
    "七人": 7,
    "八人": 8,
    "九人": 9,
    "十人": 10,
}
_DATE_PENDING_MARKERS = (
    "日期待定",
    "时间待定",
    "日期还没定",
    "日期没定",
    "具体日期还没定",
    "具体日期没定",
    "暂未定日期",
    "暂时不确定日期",
)


class RequirementCollectionError(ValueError):
    """需求补齐阶段可映射为稳定 HTTP 错误码的异常。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _days_from_text(text: str) -> int | None:
    # 先匹配“天”；数字“日”只接受“3 日游/3 日行程”，避免把 10 月 1 日识别成 1 天游。
    match = re.search(r"(\d{1,2})\s*天", text)
    if match:
        days = int(match.group(1))
        if days not in (1, 2, 3, 4, 5):
            raise RequirementCollectionError(
                "invalid_slot_value", "MVP 只支持 1-5 天行程，请选择 1-5 天"
            )
        return days
    for marker, value in _DAYS.items():
        if marker in text:
            return value
    match = re.search(r"([1-3])\s*日(?:游|行程)", text)
    if match:
        return int(match.group(1))
    return None


def _infer_year(month: int, day: int) -> int:
    """无年份的月日输入，推断为最近的未来日期。"""
    today = date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year + 1
    return today.year if candidate >= today else today.year + 1


def _date_from_text(text: str) -> date | None:
    # 带年份：2026年8月30日 / 2026-8-30 / 2026/8/30
    match = re.search(r"(20\d{2})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?", text)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    else:
        # 无年份：8月30日 / 8月30号 / 8.30 / 8-30
        match = re.search(r"(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*[日号]?", text)
        if match is None:
            return None
        month, day = int(match.group(1)), int(match.group(2))
        year = _infer_year(month, day)
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise RequirementCollectionError("invalid_slot_value", "出行日期无效") from exc


class RequirementCollector:
    """合并自然语言和结构化回答，并决定下一次追问。"""

    def __init__(self, intent_parser=None):
        # intent_parser=None 表示纯规则；调用方（生产 API）负责注入 get_intent_parser()。
        self.intent_parser = intent_parser

    def collect(
        self,
        text: str,
        *,
        current: RequirementsSnapshot | dict[str, Any] | None = None,
        structured_answer: StructuredAnswer | dict[str, Any] | None = None,
    ) -> RequirementCollectionResult:
        normalized_text = text.strip()
        if not normalized_text:
            raise RequirementCollectionError("invalid_slot_value", "消息内容不能为空")

        requirements = self._copy_current(current)
        answer = self._parse_answer(structured_answer)
        if answer is not None:
            self._assert_answer_allowed(requirements, answer)

        try:
            check_city(normalized_text)
        except AppError as exc:
            raise RequirementCollectionError(
                "unsupported_city", "北京 MVP 暂不支持其他城市"
            ) from exc

        self._merge_text(requirements, normalized_text)
        if answer is None and self.intent_parser is not None:
            # 自由文本才用 LLM 识别意图；结构化按钮回答不调用，避免无谓延迟。
            intent = self.intent_parser.parse(normalized_text, requirements)
            if intent is not None:
                self._merge_intent(requirements, intent)
        if answer is not None:
            # 结构化值来自用户实际操作的控件，是该轮确定性事实；text 只承担可读展示。
            self._apply_answer(requirements, answer)
        requirements = RequirementsSnapshot.model_validate(requirements.model_dump())
        clarification = self._next_clarification(requirements)
        return RequirementCollectionResult(
            requirements=requirements,
            clarification=clarification,
            ready=not requirements.missing_slots,
        )

    @staticmethod
    def _copy_current(
        current: RequirementsSnapshot | dict[str, Any] | None,
    ) -> RequirementsSnapshot:
        if current is None:
            return RequirementsSnapshot()
        if isinstance(current, RequirementsSnapshot):
            return current.model_copy(deep=True)
        return RequirementsSnapshot.model_validate(current)

    @staticmethod
    def _parse_answer(
        answer: StructuredAnswer | dict[str, Any] | None,
    ) -> DaysAnswer | StartDateAnswer | PaceAnswer | None:
        if answer is None:
            return None
        try:
            return _ANSWER_ADAPTER.validate_python(answer)
        except ValidationError as exc:
            raise RequirementCollectionError("invalid_slot_value", "结构化回答无效") from exc

    @staticmethod
    def _assert_answer_allowed(
        requirements: RequirementsSnapshot,
        answer: DaysAnswer | StartDateAnswer | PaceAnswer,
    ) -> None:
        if answer.slot == "days":
            if requirements.days is not None:
                raise RequirementCollectionError(
                    "clarification_already_answered", "游玩天数已经回答"
                )
            return

        if answer.slot == "pace":
            if requirements.pace is not None:
                raise RequirementCollectionError(
                    "clarification_already_answered", "旅行节奏已经回答"
                )
            return

        if requirements.date_status != "unknown":
            raise RequirementCollectionError(
                "clarification_already_answered", "出行日期已经回答"
            )

    @staticmethod
    def _apply_answer(
        requirements: RequirementsSnapshot,
        answer: DaysAnswer | StartDateAnswer | PaceAnswer,
    ) -> None:
        if answer.slot == "days":
            requirements.days = answer.value
            return
        if answer.slot == "pace":
            requirements.pace = answer.value
            return
        if answer.value == "pending":
            requirements.date_status = "pending"
            requirements.start_date = None
        else:
            requirements.date_status = "specified"
            requirements.start_date = answer.value

    @staticmethod
    def _merge_text(requirements: RequirementsSnapshot, text: str) -> None:
        days = _days_from_text(text)
        if days is not None:
            requirements.days = days

        parsed_date = _date_from_text(text)
        if parsed_date is not None:
            requirements.date_status = "specified"
            requirements.start_date = parsed_date
        elif any(marker in text for marker in _DATE_PENDING_MARKERS):
            requirements.date_status = "pending"
            requirements.start_date = None

        party_match = re.search(r"(\d{1,2})\s*人", text)
        if party_match:
            requirements.party_size = int(party_match.group(1))
        else:
            for marker, value in _PEOPLE.items():
                if marker in text:
                    requirements.party_size = value
                    break

        companions = [label for marker, label in (
            ("情侣", "情侣"),
            ("亲子", "亲子"),
            ("朋友", "朋友"),
            ("独自", "独自"),
        ) if marker in text]
        _append_unique(requirements.companion_types, companions)

        excluded = _extract_excluded_attractions(text)
        _append_unique(requirements.must_exclude, excluded)
        included = _remove_excluded_attractions(_extract_attractions(text), requirements.must_exclude)
        _append_unique(requirements.must_include, included)
        requirements.must_include = _remove_excluded_attractions(
            requirements.must_include, requirements.must_exclude
        )

        interests = [label for marker, label in (
            ("经典", "经典景点"),
            ("历史", "历史建筑"),
            ("古建", "历史建筑"),
            ("胡同", "胡同"),
            ("自然", "自然风景"),
            ("夜景", "城市景观"),
        ) if marker in text]
        _append_unique(requirements.interests, interests)

        photo_preferences = [label for marker, label in (
            ("人像", "人像"),
            ("夜景", "城市夜景"),
            ("古建筑", "古建筑"),
            ("古建", "古建筑"),
            ("自然风景", "自然风景"),
        ) if marker in text]
        _append_unique(requirements.photo_preferences, photo_preferences)

        if any(marker in text for marker in ("轻松", "休闲", "别太赶", "不要太赶")):
            requirements.pace = "轻松"
        elif any(marker in text for marker in ("紧凑", "赶一点", "多安排")):
            requirements.pace = "紧凑"
        elif "适中" in text:
            requirements.pace = "适中"

        lodging_text = _extract_lodging_text(text)
        if lodging_text:
            requirements.lodging_text = lodging_text

        transport = [label for marker, label in (
            ("少走路", "少走路"),
            ("少换乘", "少换乘"),
            ("公共交通", "公共交通"),
            ("打车", "打车"),
        ) if marker in text]
        _append_unique(requirements.transport_preferences, transport)

    @staticmethod
    def _merge_intent(requirements: RequirementsSnapshot, intent: IntentFields) -> None:
        """LLM 意图覆盖规则结果；None/空值不覆盖，避免清掉历史已确认信息。"""
        if intent.days is not None:
            requirements.days = intent.days
        if intent.date_status == "specified" and intent.start_date is not None:
            requirements.date_status = "specified"
            requirements.start_date = intent.start_date
        elif intent.date_status == "pending":
            requirements.date_status = "pending"
            requirements.start_date = None
        if intent.party_size is not None:
            requirements.party_size = intent.party_size
        if intent.pace is not None:
            requirements.pace = intent.pace
        if intent.lodging_text:
            requirements.lodging_text = intent.lodging_text

        for field, values in (
            ("companion_types", intent.companion_types),
            ("must_include", intent.must_include),
            ("must_exclude", intent.must_exclude),
            ("interests", intent.interests),
            ("photo_preferences", intent.photo_preferences),
            ("transport_preferences", intent.transport_preferences),
        ):
            if values:
                _append_unique(getattr(requirements, field), values)

        requirements.must_include = _remove_excluded_attractions(
            requirements.must_include, requirements.must_exclude
        )

    @staticmethod
    def _next_clarification(
        requirements: RequirementsSnapshot,
    ) -> ClarificationContent | None:
        if "days" in requirements.missing_slots:
            return ClarificationContent(
                slot="days",
                control="single_select",
                options=[
                    ClarificationOption(label="1 天", value=1),
                    ClarificationOption(label="2 天", value=2),
                    ClarificationOption(label="3 天", value=3),
                    ClarificationOption(label="4 天", value=4),
                    ClarificationOption(label="5 天", value=5),
                ],
                allow_pending=False,
            )
        if "start_date" in requirements.missing_slots:
            return ClarificationContent(
                slot="start_date",
                control="date_or_pending",
                options=[],
                allow_pending=True,
            )
        if "pace" in requirements.missing_slots:
            return ClarificationContent(
                slot="pace",
                control="single_select",
                options=[
                    ClarificationOption(label="休闲慢游", value="轻松"),
                    ClarificationOption(label="平衡型", value="适中"),
                    ClarificationOption(label="特种兵型", value="紧凑"),
                ],
                allow_pending=False,
            )
        return None

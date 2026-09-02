"""模型适配器接口、Mock 与 DeepSeek 实现。

PRD 要求实现层模型无关：真实模型、Mock 模型使用同一契约。
- parse_request：自然语言 → ParsedTripRequest（程序归一化 + Pydantic 校验）。
- plan_itinerary：返回候选 TripCandidate（仅编排：天数/顺序/主题），
  精确路线、出片点、来源、时间轴由后端 planner 确定性回填。
"""
from __future__ import annotations

import json
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from ..core.errors import AppError
from ..schemas import ParsedTripRequest
from .llm_client import LLMClient
from .map_tool import MapPOI, _ALIASES

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# 城市黑名单（程序化硬校验，不依赖模型判断）
_OTHER_CITIES = ["上海", "广州", "深圳", "杭州", "成都", "重庆", "西安", "南京", "武汉"]

_PACE = ("轻松", "适中", "紧凑")


class CandidateDay(BaseModel):
    theme: Optional[str] = None
    poi_ids: list[str] = []


class TripCandidate(BaseModel):
    """LLM/规划器输出的候选编排（不含路线/出片点/时间轴事实）。"""

    title: str
    overview: str
    days: list[CandidateDay] = []


class ModelAdapter(ABC):
    model_label: str = "unknown"

    @abstractmethod
    def parse_request(self, text: str, hints: dict) -> ParsedTripRequest:
        ...

    @abstractmethod
    def plan_itinerary(
        self,
        parsed: ParsedTripRequest,
        pois: list[MapPOI],
        route_context: list[dict],
        lodging: list[dict],
    ) -> TripCandidate:
        ...


def check_city(text: str) -> None:
    for city in _OTHER_CITIES:
        if city in text:
            raise AppError("parse_failed", f"MVP 只支持北京，暂不支持规划{city}行程", http_status=422)


def _read_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _extract_days(text: str, hints: dict) -> tuple[int, Optional[str]]:
    m = re.search(r"(\d)\s*[天日]", text)
    if m:
        d = int(m.group(1))
        if 1 <= d <= 5:
            return d, None
    cn = {"一天": 1, "两天": 2, "三天": 3, "两日": 2, "三日": 3, "一日": 1, "四天": 4, "四日": 4, "五天": 5, "五日": 5}
    for k, v in cn.items():
        if k in text:
            return v, None
    if hints.get("days") in (1, 2, 3, 4, 5):
        return hints["days"], "游玩天数由用户表单提供"
    return 2, "未明确游玩天数，默认按 2 天规划"


def _extract_attractions(text: str) -> list[str]:
    ordered: list[str] = []
    for name in _ALIASES:
        if name in text and name not in ordered:
            ordered.append(name)
    return ordered


def _extract_excluded_attractions(text: str) -> list[str]:
    """提取“不要去/避开”等明确排除语句中的已知景点。"""
    clauses = re.findall(
        r"(?:不去|不要去|不想去|别去|排除|避开|不安排|不要安排)([^，。；！？,!;?]*)",
        text,
    )
    excluded: list[str] = []
    seen_poi_ids: set[str] = set()
    for name, poi_id in sorted(_ALIASES.items(), key=lambda item: -len(item[0])):
        if poi_id in seen_poi_ids:
            continue
        if any(name in clause for clause in clauses):
            excluded.append(name)
            seen_poi_ids.add(poi_id)
    return excluded


def _remove_excluded_attractions(included: list[str], excluded: list[str]) -> list[str]:
    excluded_names = {name.strip() for name in excluded}
    excluded_poi_ids = {_ALIASES[name] for name in excluded_names if name in _ALIASES}
    return [
        name
        for name in included
        if name.strip() not in excluded_names and _ALIASES.get(name.strip()) not in excluded_poi_ids
    ]


def _extract_lodging_text(text: str) -> Optional[str]:
    """仅在用户主动提及住宿时提取原文，不为用户补造住宿。"""
    match = re.search(
        r"(?:住在|住宿在|酒店在|下榻于?)([^，。；！？,!;?]{2,40})",
        text,
    )
    if match is None:
        return None
    raw = match.group(1).strip()
    for name in sorted(_ALIASES, key=len, reverse=True):
        if name in raw:
            return name
    return raw or None


def _normalize_lodging_input(value: Any, text: str) -> Optional[dict[str, Any]]:
    raw_text = ""
    if isinstance(value, dict):
        raw_text = str(value.get("raw_text") or "").strip()
    if not raw_text:
        raw_text = _extract_lodging_text(text) or ""
    if not raw_text:
        return None
    # POI 事实只允许后续地图工具回填，不信任模型提供的匹配结果。
    return {"raw_text": raw_text, "poi_id": None, "matched_name": None}


def _coerce_date(v: Any) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, str):
        m = re.match(r"^(20\d{2})-(\d{1,2})-(\d{1,2})", v)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return None
    return None


class MockModelAdapter(ModelAdapter):
    """Mock：确定性规则实现，仅用于接口演示与测试。"""

    model_label = "mock"

    def parse_request(self, text: str, hints: dict) -> ParsedTripRequest:
        check_city(text)
        days, day_assumption = _extract_days(text, hints)
        must_exclude = _extract_excluded_attractions(text)
        must_include = _remove_excluded_attractions(_extract_attractions(text), must_exclude)
        assumptions: list[str] = []
        if day_assumption:
            assumptions.append(day_assumption)

        start_date = None
        m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
        if m:
            start_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        elif hints.get("start_date"):
            start_date = datetime.strptime(hints["start_date"], "%Y-%m-%d").date()
        end_date = start_date + timedelta(days=days - 1) if start_date else None

        companions: list[str] = []
        party_size = hints.get("party_size")
        for kw, label in [("情侣", "情侣"), ("亲子", "亲子"), ("朋友", "朋友"), ("独自", "独自")]:
            if kw in text and label not in companions:
                companions.append(label)
        if not companions:
            companions.append("独自")
        m2 = re.search(r"(\d)\s*人", text)
        if m2:
            party_size = int(m2.group(1))

        interests = []
        for kw, label in [("历史", "历史建筑"), ("古建", "历史建筑"), ("胡同", "胡同"), ("自然", "自然风景"), ("夜景", "城市景观")]:
            if kw in text and label not in interests:
                interests.append(label)
        photo_prefs = []
        for kw, label in [("古建筑", "古建筑"), ("古建", "古建筑"), ("人像", "人像"), ("夜景", "城市夜景"), ("自然风景", "自然风景"), ("拍照", "古建筑")]:
            if kw in text and label not in photo_prefs:
                photo_prefs.append(label)

        pace = None
        if "轻松" in text or "休闲" in text:
            pace = "轻松"
        elif "紧凑" in text or "赶" in text:
            pace = "紧凑"
        elif "适中" in text:
            pace = "适中"
        else:
            pace = hints.get("pace") if hints.get("pace") in _PACE else None

        transport = []
        for kw, label in [("少走路", "少走路"), ("少换乘", "少换乘"), ("省钱", "控制费用"), ("费用", "控制费用")]:
            if kw in text and label not in transport:
                transport.append(label)

        from ..schemas.request import DailyTimeWindow, LodgingInput

        daily_window = DailyTimeWindow(**hints["daily_time_window"]) if hints.get("daily_time_window") else None
        lodging_text = _extract_lodging_text(text)
        lodging_input = LodgingInput(raw_text=lodging_text) if lodging_text else None

        return ParsedTripRequest(
            request_id=f"req:{datetime.now().strftime('%Y%m%d')}:{uuid.uuid4().hex[:8]}",
            original_text=text,
            city="北京",
            start_date=start_date,
            end_date=end_date,
            days=days,
            party_size=party_size,
            companion_types=companions,
            must_include=must_include,
            must_exclude=must_exclude,
            interests=interests,
            photo_preferences=photo_prefs,
            pace=pace,
            lodging_input=lodging_input,
            daily_time_window=daily_window,
            transport_preferences=transport,
            budget_cny=None,
            rewritten_queries=[f"北京{'-'.join(interests) if interests else '经典'}行程"],
            other_constraints=[],
            assumptions=assumptions,
        )

    def plan_itinerary(
        self,
        parsed: ParsedTripRequest,
        pois: list[MapPOI],
        route_context: list[dict],
        lodging: list[dict],
    ) -> TripCandidate:
        chunks = self._chunk(pois, parsed.days)
        themes = {1: "皇城历史线", 2: "自然园林线", 3: "胡同城市线"}
        days = [
            CandidateDay(theme=themes.get(idx, f"第{idx}天"), poi_ids=[p.poi_id for p in chunk])
            for idx, chunk in enumerate(chunks, start=1)
        ]
        return TripCandidate(
            title=f"北京{parsed.days}日行程",
            overview=f"为{parsed.days}天北京行程，涵盖{'、'.join(p.canonical_name for p in pois) or '经典景点'}",
            days=days,
        )

    @staticmethod
    def _chunk(pois: list[MapPOI], n: int) -> list[list[MapPOI]]:
        if n <= 0 or not pois:
            return [pois]
        import math

        per = math.ceil(len(pois) / n)
        chunks = [pois[i * per : (i + 1) * per] for i in range(n)]
        return [c for c in chunks if c]


class DeepSeekModelAdapter(ModelAdapter):
    """真实 LLM：DeepSeek（OpenAI 兼容）实现，输出经归一化 + Pydantic 校验。"""

    model_label = "deepseek-chat"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    def parse_request(self, text: str, hints: dict) -> ParsedTripRequest:
        check_city(text)
        system = _read_prompt("parse_request.md")
        user = json.dumps({"text": text, "hints": hints}, ensure_ascii=False)
        last_err: Optional[Exception] = None
        for _ in range(2):
            try:
                data = self.client.complete_json(system, user)
                normalized = self._normalize_request(data, text, hints)
                return ParsedTripRequest.model_validate(normalized)
            except ValidationError as exc:
                last_err = exc
            except AppError as exc:
                last_err = exc
                break  # 网络/JSON 层错误，重试无意义
        raise AppError("parse_failed", f"需求解析失败：{last_err}" if last_err else "需求解析失败")

    def _normalize_request(self, data: dict, text: str, hints: dict) -> dict:
        """程序归一化：强制关键字段，不直接信任模型 JSON。"""
        days = data.get("days")
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 0
        if days not in (1, 2, 3, 4, 5):
            days = hints.get("days") if hints.get("days") in (1, 2, 3, 4, 5) else 2

        pace = data.get("pace")
        if pace not in _PACE:
            pace = None

        must_exclude = list(data.get("must_exclude") or [])
        for name in _extract_excluded_attractions(text):
            if name not in must_exclude:
                must_exclude.append(name)
        must_include = _remove_excluded_attractions(
            list(data.get("must_include") or []), must_exclude
        )

        return {
            "schema_version": "1.1.0",
            "request_id": str(data.get("request_id") or f"req:{datetime.now().strftime('%Y%m%d')}:{uuid.uuid4().hex[:8]}"),
            "original_text": text,  # 逐字保留
            "city": "北京",
            "start_date": _coerce_date(data.get("start_date")) or hints.get("start_date"),
            "end_date": _coerce_date(data.get("end_date")),
            "days": days,
            "party_size": data.get("party_size"),
            "companion_types": list(data.get("companion_types") or []),
            "must_include": must_include,
            "must_exclude": must_exclude,
            "interests": list(data.get("interests") or []),
            "photo_preferences": list(data.get("photo_preferences") or []),
            "pace": pace,
            "lodging_input": _normalize_lodging_input(data.get("lodging_input"), text),
            "daily_time_window": data.get("daily_time_window"),
            "transport_preferences": list(data.get("transport_preferences") or []),
            "budget_cny": data.get("budget_cny"),
            "rewritten_queries": list(data.get("rewritten_queries") or []),
            "other_constraints": list(data.get("other_constraints") or []),
            "assumptions": list(data.get("assumptions") or []),
        }

    def plan_itinerary(
        self,
        parsed: ParsedTripRequest,
        pois: list[MapPOI],
        route_context: list[dict],
        lodging: list[dict],
    ) -> TripCandidate:
        system = _read_prompt("plan_itinerary.md")
        user_payload = {
            "request": {
                "days": parsed.days,
                "start_date": parsed.start_date.isoformat() if parsed.start_date else None,
                "pace": parsed.pace,
                "companions": parsed.companion_types,
                "interests": parsed.interests,
                "transport_preferences": parsed.transport_preferences,
                "lodging_input": (
                    parsed.lodging_input.model_dump() if parsed.lodging_input else None
                ),
            },
            "pois": [
                {
                    "poi_id": p.poi_id,
                    "name": p.canonical_name,
                    "duration_min": p.suggested_duration_min,
                    "tags": p.tags,
                    "booking": p.booking_reminder,
                }
                for p in pois
            ],
            "route_minutes": route_context,
            "lodging": [{"name": l.get("name"), "level": l.get("level")} for l in lodging],
        }
        user = json.dumps(user_payload, ensure_ascii=False)
        last_err: Optional[Exception] = None
        for _ in range(2):
            try:
                data = self.client.complete_json(system, user)
                return TripCandidate.model_validate(data)
            except ValidationError as exc:
                last_err = exc
            except AppError as exc:
                last_err = exc
                break
        raise AppError("planning_failed", f"行程规划失败：{last_err}" if last_err else "行程规划失败")

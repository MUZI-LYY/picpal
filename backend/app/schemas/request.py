"""契约一：ParsedTripRequest v1.1.0

用户旅行需求经 LLM 解析和程序归一化后形成的结构化请求。
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "1.1.0"


class DailyTimeWindow(BaseModel):
    start: str = Field(description="每日可用开始时间，格式 HH:MM")
    end: str = Field(description="每日可用结束时间，格式 HH:MM")


class LodgingInput(BaseModel):
    """用户住宿输入。填写时保留用户原文和地图匹配结果。"""

    raw_text: str = Field(description="用户输入的住宿原文")
    poi_id: Optional[str] = Field(default=None, description="地图匹配后的 POI ID，未匹配时为 null")
    matched_name: Optional[str] = Field(default=None, description="地图匹配后的名称")


class ParsedTripRequest(BaseModel):
    """用户完整旅行需求的结构化表示。"""

    schema_version: Literal["1.1.0"] = SCHEMA_VERSION
    request_id: str = Field(description="唯一请求 ID")
    original_text: str = Field(description="用户原始输入，逐字保留")
    city: str = Field(description="城市，MVP 只允许北京")
    start_date: Optional[date] = Field(default=None, description="出行开始日期，可为 null，不得猜测")
    end_date: Optional[date] = Field(default=None, description="出行结束日期，可为 null")
    days: int = Field(description="游玩天数，1-5", ge=1, le=5)
    party_size: Optional[int] = Field(default=None, ge=1, description="人数")
    companion_types: list[str] = Field(default_factory=list, description="同行关系：独自/情侣/朋友/亲子等")
    must_include: list[str] = Field(default_factory=list, description="必去景点")
    must_exclude: list[str] = Field(default_factory=list, description="排除景点")
    interests: list[str] = Field(default_factory=list, description="游览兴趣")
    photo_preferences: list[str] = Field(default_factory=list, description="出片偏好")
    pace: Optional[Literal["轻松", "适中", "紧凑"]] = Field(default=None, description="行程节奏")
    lodging_input: Optional[LodgingInput] = Field(default=None, description="住宿输入")
    daily_time_window: Optional[DailyTimeWindow] = Field(default=None, description="每日可用时间")
    transport_preferences: list[str] = Field(default_factory=list, description="交通偏好")
    budget_cny: Optional[float] = Field(default=None, ge=0, description="总预算，仅作参考")
    rewritten_queries: list[str] = Field(default_factory=list, description="供检索使用，非用户原话")
    other_constraints: list[str] = Field(default_factory=list, description="其他约束")
    assumptions: list[str] = Field(default_factory=list, description="系统采用的可见假设")

    @field_validator("city")
    @classmethod
    def _city_beijing(cls, v: str) -> str:
        if v.strip() != "北京":
            raise ValueError("MVP 只支持北京")
        return "北京"

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: Optional[date], info) -> Optional[date]:
        start = info.data.get("start_date")
        if v is not None and start is not None and v < start:
            raise ValueError("结束日期不能早于开始日期")
        return v

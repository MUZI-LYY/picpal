"""契约三：ItineraryPlan v1.1.0

承载候选行程、住宿区域、路段、出片点和最终校验结果。
模型只能输出 status=draft 与 validation.status=pending。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .photo_spot import PhotoSpotHit

SCHEMA_VERSION = "1.1.0"


class POI(BaseModel):
    poi_id: str
    canonical_name: str
    map_source: Optional[str] = None


class RouteSegment(BaseModel):
    """相邻行程节点之间的移动方案。route_from_previous 由地图工具回填。"""

    origin_poi_id: str
    destination_poi_id: str
    recommended_mode: Literal["步行", "公共交通", "打车", "驾车"]
    duration_min: int
    distance_km: float
    cost_cny: Optional[float] = None
    walk_distance_m: Optional[int] = None
    transfers: Optional[int] = None
    reason: str


class ItineraryItem(BaseModel):
    item_id: str
    poi: POI
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    stay_duration_min: int = Field(ge=0)
    booking_reminder: Optional[str] = None
    entry_tip: Optional[str] = None
    route_from_previous: Optional[RouteSegment] = None
    photo_spots: list[PhotoSpotHit] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    day_index: int = Field(ge=1)
    date: Optional[str] = None
    theme: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    items: list[ItineraryItem] = Field(default_factory=list)


class LodgingRecommendation(BaseModel):
    area_id: str
    name: str
    level: Literal["首选", "备选", "当前住宿评估"]
    representative_station: Optional[str] = None
    reason: str
    covered_attractions: list[str] = Field(default_factory=list)
    avg_transit_min: Optional[int] = None


class Limitation(BaseModel):
    code: str
    message: str


class ValidationCheck(BaseModel):
    code: str
    severity: Literal["fail", "warning", "spot_fail"]
    message: str
    day_index: Optional[int] = None
    item_id: Optional[str] = None
    spot_id: Optional[str] = None


class ValidationResult(BaseModel):
    status: Literal["pending", "pass", "fail"] = "pending"
    checks: list[ValidationCheck] = Field(default_factory=list)
    checked_at: Optional[datetime] = None


class PlannerInfo(BaseModel):
    model: Optional[str] = None
    model_version: Optional[str] = None
    prompt_version: str = "planner-v1.1"


class ItineraryPlan(BaseModel):
    schema_version: Literal["1.1.0"] = SCHEMA_VERSION
    plan_id: str
    request_id: str
    status: Literal["draft", "validated", "failed"] = "draft"
    title: str
    overview: str
    request_summary: dict = Field(default_factory=dict)
    lodging_recommendations: list[LodgingRecommendation] = Field(default_factory=list)
    days: list[ItineraryDay] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    planner: PlannerInfo = Field(default_factory=PlannerInfo)
    generated_at: datetime

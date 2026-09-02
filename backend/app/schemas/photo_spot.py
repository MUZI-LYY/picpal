"""契约二：PhotoSpotRetrievalHit v1.1.0

为一个已经确定的景点 POI 返回最多若干个候选出片点。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.1.0"


class Coordinate(BaseModel):
    latitude: float
    longitude: float
    coordinate_system: Literal["GCJ-02", "WGS-84", "BD-09"] = "GCJ-02"


class ReferencePhoto(BaseModel):
    image_id: str
    storage_url: str
    thumbnail_url: Optional[str] = None
    source_id: str


class BestTime(BaseModel):
    type: Literal["固定时段", "日出关联", "日落关联", "亮灯后", "季节性"]
    display_text: str
    applicable_seasons: Optional[list[str]] = None
    applicable_weather: Optional[list[str]] = None
    source_ids: list[str]
    confidence: float = Field(ge=0, le=1)


class SourceRef(BaseModel):
    source_id: str
    source_platform: str
    source_author: Optional[str] = None
    source_url: str
    evidence_ids: list[str] = Field(default_factory=list)


class PhotoSpotHit(BaseModel):
    spot_id: str
    poi_id: str
    spot_name: str
    coordinate: Coordinate
    location_description: str
    location_precision: Literal["exact_poi", "named_sub_poi", "approximate"]
    reference_photos: list[ReferencePhoto] = Field(default_factory=list)
    best_time: Optional[BestTime] = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    ingestion_status: Literal["auto_verified"] = "auto_verified"
    confidence: float = Field(ge=0, le=1)


class FeaturedPhotoSpot(BaseModel):
    """首页精选卡片；公开数据可以只提供位置说明，不附带图片或来源。"""

    spot_id: str
    poi_id: str
    poi_name: str
    spot_name: str
    cover_image: Optional[ReferencePhoto] = None
    location_description: str
    best_time: Optional[BestTime] = None
    source: Optional[SourceRef] = None


class FeaturedPhotoSpotListResponse(BaseModel):
    data: list[FeaturedPhotoSpot] = Field(max_length=10)


class RetrievalQuery(BaseModel):
    photo_preferences: list[str] = Field(default_factory=list)
    planned_visit_date: Optional[str] = None
    planned_arrival_time: Optional[str] = None


class Pipeline(BaseModel):
    knowledge_index_version: str = "beijing-photo-spot-v1"
    embedding_model: Optional[str] = None
    reranker_model: Optional[str] = None
    fallback_used: bool = False


class PhotoSpotRetrievalHit(BaseModel):
    schema_version: Literal["1.1.0"] = SCHEMA_VERSION
    retrieval_run_id: str
    request_id: str
    poi_id: str
    query: RetrievalQuery = Field(default_factory=RetrievalQuery)
    pipeline: Pipeline = Field(default_factory=Pipeline)
    hits: list[PhotoSpotHit] = Field(default_factory=list)
    generated_at: datetime

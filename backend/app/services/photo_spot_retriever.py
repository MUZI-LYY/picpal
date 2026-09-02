"""出片点 RAG 检索接口与 Mock 实现。

真实 RAG（结构化过滤 + 关键词 + 向量 + 重排）属 PRD 阶段 1；
本阶段用 MockPhotoSpotRetriever 顶替，返回少量固定机位，其余景点返回空数组。
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from ..schemas.photo_spot import (
    PhotoSpotRetrievalHit,
    PhotoSpotHit,
    BestTime,
    Coordinate,
    RetrievalQuery,
    Pipeline,
)
from .photo_spot_store import PhotoSpotStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _spot(
    spot_id: str,
    poi_id: str,
    name: str,
    lat: float,
    lon: float,
    loc_desc: str,
    precision: str,
    subject: list[str],
    best_time: Optional[BestTime] = None,
) -> PhotoSpotHit:
    return PhotoSpotHit(
        spot_id=spot_id,
        poi_id=poi_id,
        spot_name=name,
        coordinate=Coordinate(latitude=lat, longitude=lon, coordinate_system="GCJ-02"),
        location_description=loc_desc,
        location_precision=precision,  # type: ignore[arg-type]
        reference_photos=[],
        best_time=best_time,
        source_refs=[],
        ingestion_status="auto_verified",
        confidence=0.92,
    )


# ---- Mock 出片点库（仅供测试，非真实数据）----
_MOCK_SPOTS: dict[str, list[PhotoSpotHit]] = {
    "map:forbidden_city": [
        _spot(
            "spot:forbidden-city:001", "map:forbidden_city", "东筒子红墙出片点",
            39.9163, 116.3972, "东筒子南段，靠近东侧红墙，站红墙对面取纵深感",
            "named_sub_poi", ["红墙", "纵深感"],
            best_time=BestTime(
                type="固定时段", display_text="上午 9:00 前",
                source_ids=["source:forbidden-city:001"], confidence=0.9,
            ),
        ),
        _spot(
            "spot:forbidden-city:002", "map:forbidden_city", "角楼出片点",
            39.9185, 116.4001, "东北角楼外侧护城河边，拍角楼与倒影",
            "named_sub_poi", ["角楼", "倒影"],
        ),
        _spot(
            "spot:forbidden-city:003", "map:forbidden_city", "太和殿广场出片点",
            39.9160, 116.3950, "太和殿广场中线，拍大殿全景与人物",
            "exact_poi", ["大殿", "人像"],
        ),
    ],
    "map:temple_of_heaven": [
        _spot(
            "spot:temple-of-heaven:001", "map:temple_of_heaven", "祈年殿正面出片点",
            39.8830, 116.4060, "祈年殿南侧中轴线，拍祈年殿全景",
            "named_sub_poi", ["祈年殿", "古建筑"],
        ),
        _spot(
            "spot:temple-of-heaven:002", "map:temple_of_heaven", "回音壁出片点",
            39.8820, 116.4065, "回音壁内侧，拍圆形围墙与人物",
            "exact_poi", ["回音壁", "人像"],
        ),
    ],
    "map:summer_palace": [
        _spot(
            "spot:summer-palace:001", "map:summer_palace", "十七孔桥出片点",
            40.0000, 116.2760, "昆明湖东岸，拍十七孔桥与倒影",
            "named_sub_poi", ["桥", "倒影"],
            best_time=BestTime(
                type="日落关联", display_text="日落前 1 小时",
                source_ids=["source:summer-palace:001"], confidence=0.85,
            ),
        ),
    ],
}


class PhotoSpotRetriever(ABC):
    @abstractmethod
    def retrieve(
        self,
        request_id: str,
        poi_id: str,
        photo_preferences: list[str],
        visit_date: Optional[str] = None,
        arrival_time: Optional[str] = None,
        limit: int = 3,
    ) -> PhotoSpotRetrievalHit:
        ...


class MockPhotoSpotRetriever(PhotoSpotRetriever):
    """Mock 出片点检索：仅返回固定机位，其余景点返回空数组。"""

    def retrieve(
        self,
        request_id: str,
        poi_id: str,
        photo_preferences: list[str],
        visit_date: Optional[str] = None,
        arrival_time: Optional[str] = None,
        limit: int = 3,
    ) -> PhotoSpotRetrievalHit:
        hits = _MOCK_SPOTS.get(poi_id, [])[:limit]
        return PhotoSpotRetrievalHit(
            retrieval_run_id=f"rr:{uuid.uuid4().hex[:12]}",
            request_id=request_id,
            poi_id=poi_id,
            query=RetrievalQuery(
                photo_preferences=photo_preferences,
                planned_visit_date=visit_date,
                planned_arrival_time=arrival_time,
            ),
            pipeline=Pipeline(fallback_used=False),
            hits=hits,
            generated_at=_now(),
        )


class RAGPhotoSpotRetriever(PhotoSpotRetriever):
    """真实 RAG 检索：结构化过滤 + 关键词检索 + 规则重排。

    数据来自结构化出片点库（经自动准入校验）；
    向量检索待 Embedding 模型选型后接入（见阶段文档）。
    """

    def __init__(self, store: Optional[PhotoSpotStore] = None):
        self.store = store or PhotoSpotStore()

    def retrieve(
        self,
        request_id: str,
        poi_id: str,
        photo_preferences: list[str],
        visit_date: Optional[str] = None,
        arrival_time: Optional[str] = None,
        limit: int = 3,
    ) -> PhotoSpotRetrievalHit:
        hits = self.store.search(poi_id, photo_preferences, limit)
        return PhotoSpotRetrievalHit(
            retrieval_run_id=f"rr:{uuid.uuid4().hex[:12]}",
            request_id=request_id,
            poi_id=poi_id,
            query=RetrievalQuery(
                photo_preferences=photo_preferences,
                planned_visit_date=visit_date,
                planned_arrival_time=arrival_time,
            ),
            pipeline=Pipeline(
                knowledge_index_version="beijing-photo-spot-v1",
                embedding_model=None,
                reranker_model=None,
                fallback_used=False,
            ),
            hits=hits,
            generated_at=_now(),
        )

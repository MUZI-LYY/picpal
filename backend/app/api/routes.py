"""API 路由。"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core import store
from ..core.config import settings
from ..core.errors import error_body
from ..services.model_adapter import DeepSeekModelAdapter, MockModelAdapter
from ..services.map_tool import MockMapTool
from ..services.amap_tool import AmapMapTool
from ..services.photo_spot_retriever import RAGPhotoSpotRetriever
from ..services.photo_spot_store import PhotoSpotStore
from ..schemas.photo_spot import FeaturedPhotoSpotListResponse
from ..services.planner import Planner
from ..services.validator import Validator

router = APIRouter(prefix="/api/v1")


def _build_planner() -> Planner:
    # 有 Key 用真实模型/地图，否则回退 Mock（无 Key 不阻塞开发）
    model = DeepSeekModelAdapter() if settings.has_real_llm else MockModelAdapter()
    map_tool = AmapMapTool() if settings.map_api_key else MockMapTool()
    return Planner(
        model=model,
        map_tool=map_tool,
        retriever=RAGPhotoSpotRetriever(),
        validator=Validator(),
    )


_planner = _build_planner()
_photo_spot_store = PhotoSpotStore()

_POI_NAMES = {
    "map:forbidden_city": "故宫博物院",
    "map:jingshan": "景山公园",
    "map:summer_palace": "颐和园",
    "map:temple_of_heaven": "天坛公园",
}


class TripCreate(BaseModel):
    text: str = Field(min_length=1, description="自然语言需求（必填）")
    days: Optional[int] = Field(default=None, ge=1, le=5)
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    pace: Optional[str] = None
    party_size: Optional[int] = None
    daily_time_window: Optional[dict] = None


@router.post("/trips", status_code=202)
def create_trip(body: TripCreate):
    task_id = store.new_task_id()
    store.store.create(
        task_id,
        input_text=body.text,
        input_fields=body.model_dump(exclude={"text"}, exclude_none=True),
    )
    _planner.start(
        task_id,
        input_text=body.text,
        input_fields=body.model_dump(exclude={"text"}, exclude_none=True),
    )
    return {"task_id": task_id, "status": "parsing"}


@router.get("/trips/{task_id}")
def get_trip(task_id: str):
    record = store.store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=error_body("not_found", "任务不存在"))
    return record


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/photo-spots/featured", response_model=FeaturedPhotoSpotListResponse)
def list_featured_photo_spots(
    city: Literal["北京"] = Query(default="北京"),
    limit: int = Query(default=5, ge=1, le=10),
):
    del city
    featured = []
    for spot in _photo_spot_store.featured(limit):
        cover = spot.reference_photos[0] if spot.reference_photos else None
        source = None
        if spot.source_refs:
            source = next(
                (
                    item
                    for item in spot.source_refs
                    if cover is not None and item.source_id == cover.source_id
                ),
                spot.source_refs[0],
            )
        featured.append(
            {
                "spot_id": spot.spot_id,
                "poi_id": spot.poi_id,
                "poi_name": _photo_spot_store.poi_name(spot.poi_id)
                or _POI_NAMES.get(spot.poi_id, spot.poi_id),
                "spot_name": spot.spot_name,
                "cover_image": cover,
                "location_description": spot.location_description,
                "best_time": spot.best_time,
                "source": source,
            }
        )
    return {"data": featured}

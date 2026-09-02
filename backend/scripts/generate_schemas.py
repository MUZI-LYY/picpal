"""生成三大契约的 JSON Schema 2020-12 文件与合法/非法示例。

运行：.venv/bin/python scripts/generate_schemas.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import ParsedTripRequest, PhotoSpotRetrievalHit, ItineraryPlan  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "schemas" / "json_schemas"
OUT.mkdir(parents=True, exist_ok=True)


def dump(name: str, schema: dict, valid: dict, invalid: dict) -> None:
    (OUT / f"{name}.schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / f"{name}.valid.example.json").write_text(
        json.dumps(valid, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / f"{name}.invalid.example.json").write_text(
        json.dumps(invalid, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# 合法示例（字段值用示例占位，不进入正式数据）
valid_request = {
    "schema_version": "1.1.0",
    "request_id": "req:20260818:0001",
    "original_text": "中秋去北京玩三天，和朋友一起，想去故宫、天坛",
    "city": "北京",
    "start_date": "2026-10-01",
    "end_date": "2026-10-03",
    "days": 3,
    "party_size": 2,
    "companion_types": ["朋友"],
    "must_include": ["故宫博物院", "天坛公园"],
    "must_exclude": [],
    "interests": ["历史建筑"],
    "photo_preferences": ["古建筑"],
    "pace": "适中",
    "lodging_input": None,
    "daily_time_window": {"start": "09:00", "end": "20:00"},
    "transport_preferences": [],
    "budget_cny": None,
    "rewritten_queries": ["北京历史建筑行程"],
    "other_constraints": [],
    "assumptions": [],
}
invalid_request = dict(valid_request, days=5)  # days 超出 1-3

valid_hit = {
    "schema_version": "1.1.0",
    "retrieval_run_id": "rr:20260818:0001",
    "request_id": "req:20260818:0001",
    "poi_id": "map:forbidden_city",
    "query": {"photo_preferences": ["古建筑"], "planned_visit_date": "2026-10-01", "planned_arrival_time": "09:00"},
    "pipeline": {"knowledge_index_version": "beijing-photo-spot-v1", "embedding_model": None, "reranker_model": None, "fallback_used": False},
    "hits": [
        {
            "spot_id": "spot:forbidden-city:001",
            "poi_id": "map:forbidden_city",
            "spot_name": "东筒子红墙出片点",
            "coordinate": {"latitude": 39.9163, "longitude": 116.3972, "coordinate_system": "GCJ-02"},
            "location_description": "东筒子南段，靠近东侧红墙",
            "location_precision": "named_sub_poi",
            "reference_photos": [],
            "best_time": None,
            "source_refs": [],
            "ingestion_status": "auto_verified",
            "confidence": 0.92,
        }
    ],
    "generated_at": "2026-08-18T12:05:00+08:00",
}
invalid_hit = copy.deepcopy(valid_hit)
invalid_hit["hits"][0]["location_description"] = ""  # 位置描述不能为空

valid_plan = {
    "schema_version": "1.1.0",
    "plan_id": "plan:req-20260818-0001:v1",
    "request_id": "req:20260818:0001",
    "status": "draft",
    "title": "北京三日行程",
    "overview": "行程摘要",
    "request_summary": {},
    "lodging_recommendations": [
        {
            "area_id": "map:qianmen",
            "name": "前门大街",
            "level": "首选",
            "representative_station": "前门地铁站",
            "reason": "位于景点分布中心",
            "covered_attractions": ["故宫博物院"],
            "avg_transit_min": 20,
        }
    ],
    "days": [
        {
            "day_index": 1,
            "date": "2026-10-01",
            "theme": "皇城建筑线",
            "start_time": "09:00",
            "end_time": "20:00",
            "items": [
                {
                    "item_id": "d1-i1",
                    "poi": {"poi_id": "map:forbidden_city", "canonical_name": "故宫博物院", "map_source": "mock"},
                    "start_time": "09:00",
                    "end_time": "12:00",
                    "stay_duration_min": 180,
                    "booking_reminder": None,
                    "route_from_previous": None,
                    "photo_spots": [],
                }
            ],
        }
    ],
    "limitations": [],
    "validation": {"status": "pending", "checks": [], "checked_at": None},
    "planner": {"model": "mock", "model_version": "0.1.0", "prompt_version": "planner-v1.1"},
    "generated_at": "2026-08-18T12:09:00+08:00",
}
invalid_plan = copy.deepcopy(valid_plan)
invalid_plan["status"] = "published"  # 非法状态值，超出 Literal 枚举

if __name__ == "__main__":
    dump("parsed_trip_request", ParsedTripRequest.model_json_schema(), valid_request, invalid_request)
    dump("photo_spot_retrieval_hit", PhotoSpotRetrievalHit.model_json_schema(), valid_hit, invalid_hit)
    dump("itinerary_plan", ItineraryPlan.model_json_schema(), valid_plan, invalid_plan)
    print("JSON Schema 与示例已生成到", OUT)

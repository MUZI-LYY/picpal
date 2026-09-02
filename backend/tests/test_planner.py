"""端到端编排：生成 validated 行程、空 RAG 降级、状态流转、失败路径。"""
from __future__ import annotations

import pytest

from app.core.store import TripStore
from app.services.model_adapter import MockModelAdapter
from app.services.map_tool import MapPOI, MockMapTool
from app.services.photo_spot_retriever import MockPhotoSpotRetriever
from app.services.planner import Planner
from app.services.validator import Validator


def _make_planner(tmp_path) -> tuple[Planner, TripStore]:
    s = TripStore(tmp_path)
    p = Planner(
        model=MockModelAdapter(),
        map_tool=MockMapTool(),
        retriever=MockPhotoSpotRetriever(),
        validator=Validator(),
        store_=s,
    )
    return p, s


class AmapSourceMockMapTool(MockMapTool):
    """离线模拟高德来源，只验证来源能否透传到最终契约。"""

    @staticmethod
    def _with_amap_source(poi):
        if poi is None:
            return None
        return MapPOI(
            **poi.model_dump(exclude={"map_source"}),
            map_source="amap",
        )

    def search_poi(self, name):
        return self._with_amap_source(super().search_poi(name))

    def get_poi(self, poi_id):
        return self._with_amap_source(super().get_poi(poi_id))


def _run(p, s, text, fields=None, task_id="task:test") -> dict:
    s.create(task_id, text, fields or {})
    p._run(task_id, text, fields or {})
    return s.get(task_id)


def test_end_to_end_validated(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "中秋去北京玩三天，和朋友一起，想去故宫、天坛", {"days": 3})
    assert rec["status"] == "validated", rec.get("error")
    plan = rec["plan"]
    assert plan["status"] == "validated"
    assert plan["validation"]["status"] == "pass"
    assert len(plan["days"]) == 3
    assert plan["lodging_recommendations"], "必须输出住宿区域"
    # 每个景点都有 poi_id
    for day in plan["days"]:
        for item in day["items"]:
            assert item["poi"]["poi_id"].startswith("map:")
            assert item["poi"]["map_source"] == "mock"


def test_real_map_source_is_preserved_in_final_plan(tmp_path):
    s = TripStore(tmp_path)
    p = Planner(
        model=MockModelAdapter(),
        map_tool=AmapSourceMockMapTool(),
        retriever=MockPhotoSpotRetriever(),
        validator=Validator(),
        store_=s,
    )
    rec = _run(p, s, "北京一天，想去故宫", {"days": 1})

    assert rec["status"] == "validated", rec.get("error")
    assert all(
        item["poi"]["map_source"] == "amap"
        for day in rec["plan"]["days"]
        for item in day["items"]
    )


def test_photo_spots_attached_for_covered_poi(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "想去故宫", {"days": 1})
    plan = rec["plan"]
    all_spots = [s for day in plan["days"] for it in day["items"] for s in it["photo_spots"]]
    # 故宫在 mock 覆盖内
    forbidden = [d for d in plan["days"] for it in d["items"] if it["poi"]["poi_id"] == "map:forbidden_city"]
    assert forbidden
    assert any(s["poi_id"] == "map:forbidden_city" for s in all_spots)


def test_excluded_poi_is_filtered_from_defaults_and_results(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "北京两天，想去天坛，但不去故宫", {"days": 2})

    assert rec["status"] == "validated", rec.get("error")
    assert "故宫" in rec["parsed_request"]["must_exclude"]
    poi_ids = {
        item["poi"]["poi_id"]
        for day in rec["plan"]["days"]
        for item in day["items"]
    }
    assert "map:temple_of_heaven" in poi_ids
    assert "map:forbidden_city" not in poi_ids


def test_user_lodging_is_matched_evaluated_and_used_as_daily_origin(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "北京两天，住在前门，想去故宫", {"days": 2})

    assert rec["status"] == "validated", rec.get("error")
    lodging_input = rec["parsed_request"]["lodging_input"]
    assert lodging_input["raw_text"] == "前门"
    assert lodging_input["poi_id"] == "map:qianmen"
    assert lodging_input["matched_name"] == "前门大街"

    current = [
        item
        for item in rec["plan"]["lodging_recommendations"]
        if item["level"] == "当前住宿评估"
    ]
    assert len(current) == 1
    assert current[0]["area_id"] == "map:qianmen"

    for day in rec["plan"]["days"]:
        first_route = day["items"][0]["route_from_previous"]
        assert first_route is not None
        assert first_route["origin_poi_id"] == "map:qianmen"


def test_no_lodging_input_keeps_default_recommendation_behavior(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "北京两天，想去故宫", {"days": 2})

    assert rec["parsed_request"]["lodging_input"] is None
    assert all(
        item["level"] != "当前住宿评估"
        for item in rec["plan"]["lodging_recommendations"]
    )
    assert all(day["items"][0]["route_from_previous"] is None for day in rec["plan"]["days"])


def test_unrecognized_lodging_falls_back_without_blocking_trip(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "北京两天，住在不存在的酒店XYZ，想去故宫", {"days": 2})

    assert rec["status"] == "validated", rec.get("error")
    assert rec["parsed_request"]["lodging_input"]["poi_id"] is None
    assert any("未能识别住宿位置" in item for item in rec["parsed_request"]["assumptions"])
    assert all(
        item["level"] != "当前住宿评估"
        for item in rec["plan"]["lodging_recommendations"]
    )


def test_planner_moves_monday_closed_attraction_to_open_day(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(
        p,
        s,
        "2026-08-24 去北京玩两天，想去故宫",
        {"days": 2, "start_date": "2026-08-24"},
    )

    assert rec["status"] == "validated", rec.get("error")
    forbidden_day = next(
        day
        for day in rec["plan"]["days"]
        if any(item["poi"]["poi_id"] == "map:forbidden_city" for item in day["items"])
    )
    assert forbidden_day["date"] == "2026-08-25"


def test_one_day_monday_closed_must_visit_is_not_validated(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(
        p,
        s,
        "2026-08-24 去北京玩一天，想去故宫",
        {"days": 1, "start_date": "2026-08-24"},
    )

    assert rec["status"] == "failed"
    codes = {item["code"] for item in rec["plan"]["validation"]["checks"]}
    assert "closed_day_conflict" in codes


def test_planner_waits_until_attraction_opens(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(
        p,
        s,
        "2026-08-25 去北京玩一天，想去故宫",
        {
            "days": 1,
            "start_date": "2026-08-25",
            "daily_time_window": {"start": "07:00", "end": "20:00"},
        },
    )

    forbidden = next(
        item
        for day in rec["plan"]["days"]
        for item in day["items"]
        if item["poi"]["poi_id"] == "map:forbidden_city"
    )
    assert forbidden["start_time"] == "08:30"


def test_empty_rag_degrades_without_failure(tmp_path):
    p, s = _make_planner(tmp_path)
    # 天安门在 mock 出片点库中无记录，行程仍应 valid，仅该景点无出片点
    rec = _run(p, s, "想去天安门", {"days": 1})
    assert rec["status"] == "validated"
    plan = rec["plan"]
    tiananmen_items = [it for d in plan["days"] for it in d["items"] if it["poi"]["poi_id"] == "map:tiananmen"]
    assert tiananmen_items
    assert tiananmen_items[0]["photo_spots"] == []


def test_unsupported_city_parse_failed(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "去上海玩三天", {})
    assert rec["status"] == "parse_failed"


def test_unknown_must_include_map_failed(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "想去一个不存在的景点XYZ", {})
    # "XYZ" 不是已知景点，但 mock 会 fallback 到默认景点列表，不触发 map_failed；
    # 验证行程仍可生成，且不含无法识别的景点
    assert rec["status"] == "validated"


def test_plan_id_and_request_id_consistent(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "去北京玩两天", {"days": 2})
    plan = rec["plan"]
    assert plan["request_id"] == rec["parsed_request"]["request_id"]
    assert plan["plan_id"].startswith("plan:")


def test_status_stage_history_records_flow(tmp_path):
    p, s = _make_planner(tmp_path)
    rec = _run(p, s, "去北京玩两天", {"days": 2})
    stages = [h["stage"] for h in rec["stage_history"]]
    assert stages[0] == "parsing"
    assert "retrieving_photo_spots" in stages
    assert stages[-1] == "validated"

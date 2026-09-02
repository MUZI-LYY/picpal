"""确定性校验器规则逐条触发测试。"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.schemas import (
    ItineraryPlan,
    ItineraryDay,
    ItineraryItem,
    LodgingRecommendation,
    PhotoSpotHit,
    PhotoSpotRetrievalHit,
    ReferencePhoto,
    SourceRef,
    Coordinate,
)
from app.services.validator import Validator

validator = Validator()


def _spot(spot_id="spot:1", poi_id="map:forbidden_city", name="测试机位"):
    return PhotoSpotHit(
        spot_id=spot_id, poi_id=poi_id, spot_name=name,
        coordinate=Coordinate(latitude=39.9, longitude=116.4),
        location_description="站在红墙边",
        location_precision="named_sub_poi",
        reference_photos=[ReferencePhoto(image_id="img:1", storage_url="https://e.invalid/a.jpg", source_id="source:1")],
        source_refs=[SourceRef(source_id="source:1", source_platform="example", source_url="https://e.invalid/s")],
        ingestion_status="auto_verified", confidence=0.9,
    )


def _hit(poi_id, spots):
    return PhotoSpotRetrievalHit(
        retrieval_run_id="rr:1", request_id="req:1", poi_id=poi_id,
        hits=spots, generated_at=datetime.now(timezone.utc),
    )


def _lodging():
    return [LodgingRecommendation(area_id="map:qianmen", name="前门", level="首选", reason="居中")]


def _plan(items_per_day, lodging=None, overview="行程", dates=None):
    days = []
    for i, items in enumerate(items_per_day, start=1):
        date = dates[i - 1] if dates else None
        days.append(ItineraryDay(day_index=i, date=date, items=items))
    return ItineraryPlan(
        plan_id="plan:1", request_id="req:1", title="测试", overview=overview,
        lodging_recommendations=lodging if lodging is not None else _lodging(),
        days=days, generated_at=datetime.now(timezone.utc),
    )


def _item(item_id, poi_id, start="09:00", end="10:00", spots=None):
    return ItineraryItem(
        item_id=item_id, poi={"poi_id": poi_id, "canonical_name": poi_id},
        start_time=start, end_time=end, stay_duration_min=60,
        photo_spots=spots or [],
    )


def _codes(checks):
    return {c.code for c in checks}


def _map_poi(open_time="08:30", close_time="17:00", closed_weekdays=None):
    hours = SimpleNamespace(
        open_time=open_time,
        close_time=close_time,
        closed_weekdays=closed_weekdays or [],
    )
    return SimpleNamespace(canonical_name="故宫博物院", operating_hours=hours)


def test_missing_map_poi_fails():
    plan = _plan([[ _item("d1-i1", "map:not_exist") ]])
    checks = validator.validate(plan, {"map:forbidden_city"}, {})
    assert "missing_map_poi" in _codes(checks)
    assert any(c.severity == "fail" for c in checks if c.code == "missing_map_poi")


def test_duplicate_poi_warns():
    plan = _plan([[ _item("d1-i1", "map:x"), _item("d1-i2", "map:x", "11:00", "12:00") ]])
    checks = validator.validate(plan, {"map:x"}, {})
    assert "duplicate_poi" in _codes(checks)


def test_time_conflict_fails():
    plan = _plan([[ _item("d1-i1", "map:x", "09:00", "11:00"), _item("d1-i2", "map:y", "10:00", "12:00") ]])
    checks = validator.validate(plan, {"map:x", "map:y"}, {})
    assert "time_conflict" in _codes(checks)


def test_closed_day_conflict_fails():
    plan = _plan(
        [[_item("d1-i1", "map:forbidden_city")]],
        dates=["2026-08-24"],  # 周一
    )
    checks = validator.validate(
        plan,
        {"map:forbidden_city"},
        {},
        map_pois={"map:forbidden_city": _map_poi(closed_weekdays=[0])},
    )
    assert "closed_day_conflict" in _codes(checks)
    assert any(c.severity == "fail" for c in checks if c.code == "closed_day_conflict")


def test_outside_open_hours_fails():
    plan = _plan(
        [[_item("d1-i1", "map:forbidden_city", "16:00", "18:00")]],
        dates=["2026-08-25"],
    )
    checks = validator.validate(
        plan,
        {"map:forbidden_city"},
        {},
        map_pois={"map:forbidden_city": _map_poi()},
    )
    assert "outside_open_hours" in _codes(checks)
    assert any(c.severity == "fail" for c in checks if c.code == "outside_open_hours")


def test_known_open_hours_allow_valid_visit():
    plan = _plan(
        [[_item("d1-i1", "map:forbidden_city", "09:00", "12:00")]],
        dates=["2026-08-25"],
    )
    checks = validator.validate(
        plan,
        {"map:forbidden_city"},
        {},
        map_pois={"map:forbidden_city": _map_poi()},
    )
    assert "closed_day_conflict" not in _codes(checks)
    assert "outside_open_hours" not in _codes(checks)


def test_unknown_open_hours_warns_without_failing():
    plan = _plan([[_item("d1-i1", "map:x")]], dates=["2026-08-25"])
    checks = validator.validate(
        plan,
        {"map:x"},
        {},
        map_pois={"map:x": SimpleNamespace(canonical_name="未知景点", operating_hours=None)},
    )
    assert "unknown_open_hours" in _codes(checks)
    assert not any(c.severity == "fail" for c in checks if c.code == "unknown_open_hours")


def test_excessive_density_fails():
    items = [_item(f"d1-i{i}", f"map:p{i}", f"{9+i:02d}:00", f"{10+i:02d}:00") for i in range(1, 7)]
    plan = _plan([items])
    checks = validator.validate(plan, {f"map:p{i}" for i in range(1, 7)}, {})
    assert "excessive_density" in _codes(checks)


def test_missing_route_data_warns():
    from app.schemas import RouteSegment
    day_items = [
        _item("d1-i1", "map:x"),
        _item("d1-i2", "map:y", "11:00", "12:00"),  # 第二个节点无 route_from_previous
    ]
    plan = _plan([day_items])
    checks = validator.validate(plan, {"map:x", "map:y"}, {})
    assert "missing_route_data" in _codes(checks)


def test_stale_claim_warns():
    plan = _plan([[_item("d1-i1", "map:x")]], overview="实时客流较大")
    checks = validator.validate(plan, {"map:x"}, {})
    assert "stale_claim" in _codes(checks)


def test_invalid_photo_spot_spot_fail():
    spot = _spot(spot_id="spot:foreign", poi_id="map:other")  # 不属于当前景点
    plan = _plan([[_item("d1-i1", "map:x", spots=[spot])]])
    hits = {"map:x": _hit("map:x", [_spot(spot_id="spot:valid")])}
    checks = validator.validate(plan, {"map:x"}, hits)
    assert "invalid_photo_spot" in _codes(checks)
    assert any(c.severity == "spot_fail" for c in checks if c.code == "invalid_photo_spot")


def test_missing_spot_coordinate_spot_fail():
    spot = _spot()
    spot.coordinate = None  # type: ignore[assignment]
    plan = _plan([[_item("d1-i1", "map:forbidden_city", spots=[spot])]])
    hits = {"map:forbidden_city": _hit("map:forbidden_city", [spot])}
    checks = validator.validate(plan, {"map:forbidden_city"}, hits)
    assert "missing_spot_coordinate" in _codes(checks)


def test_missing_location_description_spot_fail():
    spot = _spot()
    spot.location_description = ""
    plan = _plan([[_item("d1-i1", "map:forbidden_city", spots=[spot])]])
    hits = {"map:forbidden_city": _hit("map:forbidden_city", [spot])}
    checks = validator.validate(plan, {"map:forbidden_city"}, hits)
    assert "missing_location_description" in _codes(checks)


def test_missing_photo_is_allowed_for_public_location_record():
    spot = _spot()
    spot.reference_photos = []
    plan = _plan([[_item("d1-i1", "map:forbidden_city", spots=[spot])]])
    hits = {"map:forbidden_city": _hit("map:forbidden_city", [spot])}
    checks = validator.validate(plan, {"map:forbidden_city"}, hits)
    assert "missing_photo_source" not in _codes(checks)


def test_unsupported_best_time_spot_fail():
    from app.schemas import BestTime
    spot = _spot()
    spot.best_time = BestTime(type="固定时段", display_text="上午", source_ids=[], confidence=0.9)
    plan = _plan([[_item("d1-i1", "map:forbidden_city", spots=[spot])]])
    hits = {"map:forbidden_city": _hit("map:forbidden_city", [spot])}
    checks = validator.validate(plan, {"map:forbidden_city"}, hits)
    assert "unsupported_best_time" in _codes(checks)


def test_missing_lodging_recommendation_fails():
    plan = _plan([[_item("d1-i1", "map:x")]], lodging=[])
    checks = validator.validate(plan, {"map:x"}, {})
    assert "missing_lodging_recommendation" in _codes(checks)


def test_clean_plan_has_no_fail():
    plan = _plan([[_item("d1-i1", "map:x")]])
    checks = validator.validate(plan, {"map:x"}, {})
    assert not any(c.severity == "fail" for c in checks)

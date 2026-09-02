"""高德工具纯函数测试（离线，不依赖网络）。"""
from __future__ import annotations

from app.services.amap_tool import (
    AmapMapTool,
    estimate_taxi_cny,
    parse_location,
    _resolve_internal_id,
)
from app.services.map_tool import MockMapTool


def test_parse_location_lng_lat_order():
    # 高德 location 是 "经度,纬度"
    c = parse_location("116.3972,39.9163")
    assert c is not None
    assert c.longitude == 116.3972
    assert c.latitude == 39.9163
    assert c.coordinate_system == "GCJ-02"


def test_parse_location_invalid():
    assert parse_location("") is None
    assert parse_location("abc") is None
    assert parse_location("116.3972") is None


def test_estimate_taxi():
    assert estimate_taxi_cny(2.0) == 13.0
    assert estimate_taxi_cny(5.0) == round(13 + 2.3 * 2, 1)


def test_resolve_internal_id():
    assert _resolve_internal_id("故宫") == "map:forbidden_city"
    assert _resolve_internal_id("故宫博物院") == "map:forbidden_city"
    assert _resolve_internal_id("不存在的景点XYZ") is None


def test_phase1_all_30_attractions_have_stable_internal_ids():
    expected = {
        "故宫": "map:forbidden_city",
        "天安门": "map:tiananmen",
        "前门": "map:qianmen",
        "国家博物馆": "map:national_museum",
        "王府井": "map:wangfujing",
        "天坛": "map:temple_of_heaven",
        "恭王府": "map:prince_gongs_mansion",
        "南锣鼓巷": "map:nanluoguxiang",
        "钟鼓楼": "map:bell_drum_towers",
        "国贸": "map:guomao",
        "颐和园": "map:summer_palace",
        "圆明园": "map:old_summer_palace",
        "雍和宫": "map:yonghe_temple",
        "环球度假区": "map:universal_beijing",
        "北京动物园": "map:beijing_zoo",
        "景山": "map:jingshan",
        "北海公园": "map:beihai_park",
        "什刹海": "map:shichahai",
        "香山": "map:fragrant_hills",
        "潭柘寺": "map:tanzhe_temple",
        "八达岭": "map:badaling",
        "奥林匹克公园": "map:olympic_park",
        "古北水镇": "map:gubei_water_town",
        "明十三陵": "map:ming_tombs",
        "首钢园": "map:shougang_park",
        "慕田峪": "map:mutianyu",
        "798艺术区": "map:798_art_district",
        "亮马河": "map:liangma_river",
        "北京野生动物园": "map:beijing_wildlife_park",
        "北京大运河": "map:beijing_grand_canal",
    }
    tool = MockMapTool()

    assert {_resolve_internal_id(name) for name in expected} == set(expected.values())
    assert all(tool.search_poi(name) is not None for name in expected)


def test_amap_poi_is_labeled_with_real_source():
    tool = AmapMapTool(api_key="test-key")
    poi = tool._build_poi(
        "amap:test-poi",
        {"id": "test-poi", "name": "测试景点", "address": "北京市", "location": "116.4,39.9"},
    )
    assert poi.map_source == "amap"


def test_route_options_cache_does_not_leak_recommendation_between_preferences(monkeypatch):
    tool = AmapMapTool(api_key="test-key")
    mock_map = MockMapTool()
    tool._cache["map:forbidden_city"] = mock_map.get_poi("map:forbidden_city")
    tool._cache["map:summer_palace"] = mock_map.get_poi("map:summer_palace")

    calls: list[str] = []

    def fake_direction(kind, origin, destination):
        calls.append(kind)
        if kind == "walking":
            return {"duration_min": 120, "distance_km": 10.0, "distance_m": 10000}
        if kind == "transit":
            return {"duration_min": 45, "distance_km": 10.0}
        return {"duration_min": 30, "distance_km": 10.0}

    monkeypatch.setattr(tool, "_direction", fake_direction)

    normal = tool.get_route("map:forbidden_city", "map:summer_palace", [])
    less_walking = tool.get_route(
        "map:forbidden_city", "map:summer_palace", ["少走路"]
    )

    assert normal is not None and normal.recommended_mode == "公共交通"
    assert less_walking is not None and less_walking.recommended_mode == "打车"
    assert calls == ["walking", "transit", "driving"], "同一路段原始方案只能请求一次"

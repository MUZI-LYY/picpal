"""出片点准入管线测试（纯函数 + 依赖注入的假 LLM/地图，离线）。"""
from __future__ import annotations

from app.schemas.photo_spot import Coordinate
from app.services.admission_pipeline import (
    AdmissionPipeline,
    RANGE_KM,
    cluster_coords,
    dedup_photo_spots,
    is_beijing_attraction,
    is_exact_poi_match,
    name_similarity,
    range_limit_km,
    validate_geo_tag,
)
from app.services.map_tool import MapPOI


def _attraction() -> MapPOI:
    return MapPOI(
        poi_id="map:forbidden_city",
        canonical_name="故宫博物院",
        address="北京",
        coordinate=Coordinate(latitude=39.9163, longitude=116.3972),
        poi_type="attraction",
    )


def _summer_palace() -> MapPOI:
    return MapPOI(
        poi_id="map:summer_palace",
        canonical_name="颐和园",
        address="北京",
        coordinate=Coordinate(latitude=39.9999, longitude=116.2755),
        poi_type="attraction",
    )


# ---------- 纯函数 ----------
def test_name_similarity():
    assert name_similarity("万春亭", "万春亭") == 1.0
    assert name_similarity("万春亭", "景山万春亭") == 0.9
    assert name_similarity("红墙", "故宫博物院") == 0.0


def test_is_exact_poi_match():
    # 精确：q 是 name 的核心名（q == name 或 q 是 name 的子串）
    assert is_exact_poi_match("角楼", "角楼") is True
    assert is_exact_poi_match("画中游", "颐和园-画中游") is True
    # 近似：q 比 name 长（含方位/设施修饰）
    assert is_exact_poi_match("南湖岛下船处", "南湖岛") is False
    assert is_exact_poi_match("万春亭北面", "寿皇殿") is False


def test_exact_match_preferred_over_substring():
    # 精确相等的"知春亭"优先，忽略包含匹配的"知春亭茶饮"奶茶店（避免坐标被拉偏）
    class Map:
        def search_poi(self, name):
            return _summer_palace()

        def search_raw(self, keyword, city="北京", offset=10):
            if keyword == "知春亭":
                return [
                    {"name": "知春亭", "location": "116.279369,39.996690"},
                    {"name": "知春亭茶饮·颐和园", "location": "116.279969,39.997032"},
                ]
            return []

    p = AdmissionPipeline(llm=FakeLLM({}), map_tool=Map())  # type: ignore[arg-type]
    coord, is_exact = p._unique_match_sub_poi("知春亭", _summer_palace())
    assert coord is not None
    assert coord.longitude == 116.279369  # 精确的亭子，不是聚类中心
    assert coord.latitude == 39.996690
    assert is_exact is True


def test_validate_geo_tag_in_range():
    coord = Coordinate(latitude=39.9163, longitude=116.3972)  # 景点中心附近
    assert validate_geo_tag(coord, _attraction()) is not None


def test_validate_geo_tag_out_of_range():
    coord = Coordinate(latitude=40.5, longitude=117.0)  # 几十公里外
    assert validate_geo_tag(coord, _attraction()) is None


def test_unreviewed_phase1_range_cannot_auto_admit_coordinates():
    attraction = MapPOI(
        poi_id="map:national_museum",
        canonical_name="中国国家博物馆",
        address="北京",
        coordinate=Coordinate(latitude=39.9051, longitude=116.4013),
        poi_type="attraction",
    )
    same_center = Coordinate(latitude=39.9051, longitude=116.4013)

    assert range_limit_km("map:national_museum") is None
    assert validate_geo_tag(same_center, attraction) is None


def test_cluster_coords():
    a = Coordinate(latitude=39.916, longitude=116.397)
    b = Coordinate(latitude=39.91605, longitude=116.3971)  # 约 10 米内
    c = Coordinate(latitude=39.99, longitude=116.30)  # 远处
    clusters = cluster_coords([a, b, c], radius_m=100)
    # a、b 应聚为一簇，c 独立
    assert len(clusters) == 2
    sizes = sorted(len(cl) for cl in clusters)
    assert sizes == [1, 2]


# ---------- 管线（假 LLM + 假地图） ----------
class FakeLLM:
    def __init__(self, evidence: dict):
        self.evidence = evidence

    def complete_json(self, system, user, **kw):
        return self.evidence


class FakeMap:
    def search_poi(self, name):
        return _attraction()

    def search_raw(self, keyword, city="北京", offset=10):
        # 模拟：搜"角楼"返回唯一匹配，搜其他返回空
        if keyword == "角楼":
            return [{"name": "角楼", "location": "116.4009,39.9197"}]
        return []


def _pipeline(evidence: dict, note: dict) -> AdmissionPipeline:
    return AdmissionPipeline(llm=FakeLLM(evidence), map_tool=FakeMap())  # type: ignore[arg-type]


_SPOT_EVIDENCE = {
    "attraction": "故宫",
    "level": "spot",
    "has_explicit_location": True,
    "sub_poi_names": ["角楼"],
    "spots": [
        {
            "spot_name": "角楼",
            "location_description": "东北角楼外侧护城河边",
            "location_precision": "named_sub_poi",
            "photo_subjects": ["角楼"],
            "visual_styles": ["夜景"],
            "best_time": None,
        }
    ],
}


def test_attraction_level_goes_candidate():
    p = _pipeline({"attraction": "故宫", "level": "attraction", "has_explicit_location": False, "sub_poi_names": [], "spots": []}, {})
    r = p.process_note({"text": "故宫里面很好拍"})
    assert r.status == "candidate"


def test_sub_poi_unique_match_auto_verified():
    p = _pipeline(_SPOT_EVIDENCE, {})
    r = p.process_note({"text": "站在角楼外护城河边拍倒影"})
    assert r.status == "auto_verified"
    assert r.coordinate is not None
    assert "map_unique_match" in r.admission_evidence


def test_geo_tag_auto_verified():
    p = _pipeline(_SPOT_EVIDENCE, {})
    r = p.process_note({"text": "...", "geo": {"lng": 116.3972, "lat": 39.9163}})
    assert r.status == "auto_verified"
    assert "geo_tag_in_range" in r.admission_evidence


def test_no_location_evidence_candidate():
    # 子POI搜不到 + 机位名搜不到 + 无geo标签 + 位置表达匹配不到 → candidate
    evidence = dict(_SPOT_EVIDENCE, sub_poi_names=["红墙"], has_explicit_location=False)
    evidence["spots"] = [dict(_SPOT_EVIDENCE["spots"][0], spot_name="红墙")]
    p = _pipeline(evidence, {})
    r = p.process_note({"text": "故宫红墙很好拍"})
    assert r.status == "candidate"


def test_unknown_attraction_rejected():
    class NoMap:
        def search_poi(self, name):
            return None

        def search_raw(self, keyword, city="北京", offset=10):
            return []

    p = AdmissionPipeline(llm=FakeLLM(_SPOT_EVIDENCE), map_tool=NoMap())  # type: ignore[arg-type]
    r = p.process_note({"text": "..."})
    assert r.status == "rejected"


# ---------- 跨城市同名景点拦截 ----------
def test_is_beijing_attraction():
    assert is_beijing_attraction("景山公园") is True
    assert is_beijing_attraction("北京景山公园") is True
    assert is_beijing_attraction("故宫") is True
    assert is_beijing_attraction("珠海景山公园") is False
    assert is_beijing_attraction("上海外滩") is False
    assert is_beijing_attraction("") is False


def test_non_beijing_attraction_rejected():
    evidence = dict(_SPOT_EVIDENCE, attraction="珠海景山公园")
    p = _pipeline(evidence, {})
    r = p.process_note({"text": "珠海景山公园山顶"})
    assert r.status == "rejected"
    assert "非北京景点" in r.reason


def test_directional_spot_goes_candidate():
    # 机位名含方位/设施修饰（近似匹配到父 POI）→ candidate，不上线
    evidence = {
        "attraction": "故宫",
        "level": "spot",
        "has_explicit_location": True,
        "sub_poi_names": [],
        "spots": [
            {"spot_name": "南湖岛下船处", "location_description": "南湖岛下船处", "location_precision": "named_sub_poi", "photo_subjects": [], "visual_styles": [], "best_time": None}
        ],
    }

    class Map:
        def search_poi(self, name):
            return _attraction()

        def search_raw(self, keyword, city="北京", offset=10):
            # "南湖岛下船处" 只能匹配到父 POI "南湖岛"
            if keyword == "南湖岛下船处":
                return [{"name": "南湖岛", "location": "116.3972,39.9163"}]
            return []

    p = AdmissionPipeline(llm=FakeLLM(evidence), map_tool=Map())  # type: ignore[arg-type]
    r = p.process_note({"text": "南湖岛下船处"})
    assert r.status == "candidate"
    assert "近似" in r.reason or "非精确" in r.reason


# ---------- 多源去重 ----------
def _spot_record(spot_name, lng, lat, source_id, url):
    return {
        "spot_id": f"spot:x:{source_id}",
        "poi_id": "map:forbidden_city",
        "spot_name": spot_name,
        "coordinate": {"latitude": lat, "longitude": lng, "coordinate_system": "GCJ-02"},
        "location_description": spot_name,
        "location_precision": "named_sub_poi",
        "photo_subjects": ["角楼"],
        "visual_styles": ["夜景"],
        "reference_photos": [{"image_id": f"i-{source_id}", "storage_url": url, "source_id": source_id}],
        "source_refs": [{"source_id": source_id, "source_platform": "example", "source_url": "http://x", "evidence_ids": ["e1"]}],
        "ingestion_status": "auto_verified",
        "admission_evidence": ["map_unique_match"],
        "confidence": 0.7,
    }


def test_dedup_photo_spots_merges_nearby_and_keeps_far():
    r1 = _spot_record("角楼", 116.4009, 39.9197, "s1", "http://img/1")
    r2 = _spot_record("角楼", 116.40095, 39.91975, "s2", "http://img/2")  # 约 10 米内
    r3 = _spot_record("太和门", 116.3972, 39.9151, "s3", "http://img/3")  # 远处
    out = dedup_photo_spots([r1, r2, r3])
    assert len(out) == 2
    jiaolou = next(o for o in out if o["spot_name"] == "角楼")
    assert jiaolou["confidence"] > 0.7  # 多源置信度提高
    assert len(jiaolou["source_refs"]) == 2  # 两个来源合并
    assert len(jiaolou["reference_photos"]) == 2


def test_duplicate_rows_from_same_source_do_not_increase_confidence():
    r1 = _spot_record("角楼", 116.4009, 39.9197, "s1", "http://img/1")
    r2 = _spot_record("角楼", 116.40091, 39.91971, "s1", "http://img/1-copy")

    out = dedup_photo_spots([r1, r2])

    assert len(out) == 1
    assert out[0]["confidence"] == 0.7
    assert len(out[0]["source_refs"]) == 1


# ---------- 多机位拆分 ----------
class FakeMapMulti:
    """对不同机位名返回不同坐标。"""

    def search_poi(self, name):
        return _attraction()

    def search_raw(self, keyword, city="北京", offset=10):
        coords = {
            "角楼": [{"name": "角楼", "location": "116.4009,39.9197"}],
            "太和门": [{"name": "太和门", "location": "116.3972,39.9151"}],
        }
        return coords.get(keyword, [])


def test_process_note_all_splits_multiple_spots():
    evidence = {
        "attraction": "故宫",
        "level": "spot",
        "has_explicit_location": True,
        "sub_poi_names": [],
        "spots": [
            {"spot_name": "角楼", "location_description": "角楼外", "location_precision": "named_sub_poi", "photo_subjects": [], "visual_styles": [], "best_time": None},
            {"spot_name": "太和门", "location_description": "太和门前", "location_precision": "named_sub_poi", "photo_subjects": [], "visual_styles": [], "best_time": None},
        ],
    }
    p = AdmissionPipeline(llm=FakeLLM(evidence), map_tool=FakeMapMulti())  # type: ignore[arg-type]
    results = p.process_note_all({"text": "角楼和太和门都出片"})
    assert len(results) == 2
    assert all(r.status == "auto_verified" for r in results)
    assert results[0].coordinate.latitude == 39.9197
    assert results[1].coordinate.latitude == 39.9151

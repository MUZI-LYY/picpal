"""出片点结构化库 + RAG 检索测试（离线）。"""
from __future__ import annotations

from app.services.photo_spot_store import (
    PhotoSpotStore,
    local_photo_url,
)
from app.services.photo_spot_retriever import RAGPhotoSpotRetriever


def _store(tmp_path):
    # 用内置种子数据
    from app.services.photo_spot_store import DEFAULT_DATA_PATH

    return PhotoSpotStore(DEFAULT_DATA_PATH)


def test_seed_data_loads():
    s = _store(None)
    assert s.count() == 24
    assert "map:forbidden_city" in s.records
    photos = [photo for spots in s.records.values() for spot in spots for photo in spot.reference_photos]
    sources = [source for spots in s.records.values() for spot in spots for source in spot.source_refs]
    assert photos == []
    assert sources == []


def test_missing_local_photo_returns_no_url():
    assert local_photo_url("image:000000000000000000000000:0") is None


def test_search_returns_top3():
    s = _store(None)
    hits = s.search("map:forbidden_city", [], limit=3)
    assert 0 < len(hits) <= 3
    assert all(h.poi_id == "map:forbidden_city" for h in hits)


def test_search_empty_for_uncovered_poi():
    s = _store(None)
    assert s.search("map:tiananmen", [], 3) == []


def test_featured_uses_admitted_records_and_covers_multiple_pois():
    s = _store(None)
    hits = s.featured(limit=5)

    assert len(hits) == 5
    assert len({hit.poi_id for hit in hits}) >= 4
    assert all(hit.reference_photos == [] for hit in hits)
    assert all(hit.source_refs == [] for hit in hits)


def test_keyword_preference_boosts():
    s = _store(None)
    plain = s.search("map:forbidden_city", [], 3)
    with_night = s.search("map:forbidden_city", ["城市夜景"], 3)
    # 夜景偏好下，角楼（含夜景标签）应排在更靠前
    def rank(hits, spot_id):
        for i, h in enumerate(hits):
            if h.spot_id == spot_id:
                return i
        return 99

    assert rank(with_night, "spot:forbidden-city:001") <= rank(plain, "spot:forbidden-city:001")


def test_admit_rules(tmp_path):
    valid = {
        "spot_id": "s1", "poi_id": "map:x", "spot_name": "n",
        "coordinate": {"latitude": 1, "longitude": 1, "coordinate_system": "GCJ-02"},
        "location_description": "d", "location_precision": "named_sub_poi",
        "reference_photos": [],
        "source_refs": [],
        "ingestion_status": "auto_verified", "review_status": "approved",
        "publication_rights_status": "approved",
        "admission_evidence": ["explicit_location"],
    }
    assert PhotoSpotStore._admit(valid)

    # 缺坐标 → 拒绝
    bad = dict(valid, coordinate=None)
    assert not PhotoSpotStore._admit(bad)

    # 机器通过但未经独立人工批准 → 拒绝
    bad = dict(valid, review_status="pending")
    assert not PhotoSpotStore._admit(bad)

    # 未获得公开授权的数据不能由公开检索接口返回
    bad = dict(valid, publication_rights_status="internal_review_only")
    assert not PhotoSpotStore._admit(bad)

    # 非 auto_verified → 拒绝
    bad = dict(valid, ingestion_status="candidate")
    assert not PhotoSpotStore._admit(bad)

    # 位置精度不在白名单 → 拒绝
    bad = dict(valid, location_precision="fuzzy")
    assert not PhotoSpotStore._admit(bad)

    # 缺准入证据 → 拒绝
    bad = dict(valid, admission_evidence=[])
    assert not PhotoSpotStore._admit(bad)


def test_retriever_returns_contract():
    r = RAGPhotoSpotRetriever(_store(None))
    hit = r.retrieve("req:1", "map:forbidden_city", ["古建筑"], limit=3)
    assert hit.schema_version == "1.1.0"
    assert hit.poi_id == "map:forbidden_city"
    assert hit.request_id == "req:1"
    assert len(hit.hits) <= 3
    for h in hit.hits:
        assert h.ingestion_status == "auto_verified"
        assert h.reference_photos == []
        assert h.source_refs == []

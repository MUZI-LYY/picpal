"""首页精选出片点 API 可以安全返回不含图片和来源的公开记录。"""

from fastapi.testclient import TestClient

from app.main import app


def test_featured_photo_spots_match_public_contract():
    with TestClient(app) as client:
        response = client.get("/api/v1/photo-spots/featured?city=北京&limit=5")

    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 5
    assert len({item["poi_id"] for item in items}) >= 4
    for item in items:
        assert item["cover_image"] is None
        assert item["source"] is None
        assert item["location_description"]


def test_featured_photo_spots_reject_unsupported_city():
    with TestClient(app) as client:
        response = client.get("/api/v1/photo-spots/featured?city=上海")

    assert response.status_code == 422

"""地图工具接口与 Mock 实现。

真实地图服务供应商待选型；本阶段用 MockMapTool 顶替，
仅用于接口演示与测试，坐标/路线为 mock 数据，不代表真实数据。
"""
from __future__ import annotations

import math
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..schemas.photo_spot import Coordinate


class OperatingHours(BaseModel):
    """景点常规开放规则；临时闭馆和节假日调整不在本地基线内。"""

    open_time: str
    close_time: str
    closed_weekdays: list[int] = Field(default_factory=list)
    source_note: Optional[str] = None


class MapPOI(BaseModel):
    poi_id: str
    canonical_name: str
    address: str
    coordinate: Coordinate
    map_source: str = "mock"
    poi_type: str  # attraction / hotel / station / area
    tags: list[str] = []
    suggested_duration_min: int = 120
    booking_reminder: Optional[str] = None
    entry_tip: Optional[str] = None
    open_note: Optional[str] = None
    operating_hours: Optional[OperatingHours] = None


class ModeOption(BaseModel):
    mode: str  # 步行 / 公共交通 / 打车 / 驾车
    duration_min: int
    distance_km: float
    cost_cny: Optional[float] = None
    walk_distance_m: Optional[int] = None
    transfers: Optional[int] = None


class RouteQueryResult(BaseModel):
    origin_poi_id: str
    destination_poi_id: str
    options: list[ModeOption]
    recommended_mode: str
    reason: str


def _haversine_km(a: Coordinate, b: Coordinate) -> float:
    r = 6371.0
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class MapTool(ABC):
    @abstractmethod
    def search_poi(self, name: str) -> Optional[MapPOI]:
        ...

    @abstractmethod
    def get_poi(self, poi_id: str) -> Optional[MapPOI]:
        ...

    @abstractmethod
    def get_route(
        self, origin_poi_id: str, destination_poi_id: str, transport_preferences: list[str]
    ) -> Optional[RouteQueryResult]:
        ...


# ---- Mock 北京景点目录（仅供测试，非真实数据）----
_MOCK_POIS: dict[str, MapPOI] = {
    "map:forbidden_city": MapPOI(
        poi_id="map:forbidden_city",
        canonical_name="故宫博物院",
        address="北京市东城区景山前街4号",
        coordinate=Coordinate(latitude=39.9163, longitude=116.3972),
        poi_type="attraction",
        tags=["历史建筑", "古建筑"],
        suggested_duration_min=180,
        booking_reminder="需提前预约，周一闭馆",
        entry_tip="从午门进入，神武门出",
        open_note="旺季 08:30—17:00",
        operating_hours=OperatingHours(
            open_time="08:30",
            close_time="17:00",
            closed_weekdays=[0],
            source_note="沿用项目已有旺季开放时间基线，正式上线前需核对官方公告",
        ),
    ),
    "map:tiananmen": MapPOI(
        poi_id="map:tiananmen",
        canonical_name="天安门广场",
        address="北京市东城区长安街",
        coordinate=Coordinate(latitude=39.9055, longitude=116.3976),
        poi_type="attraction",
        tags=["城市景观", "历史建筑"],
        suggested_duration_min=60,
        booking_reminder="需预约",
        entry_tip="预留安检时间，从广场北侧进入中轴线",
    ),
    "map:jingshan": MapPOI(
        poi_id="map:jingshan",
        canonical_name="景山公园",
        address="北京市西城区景山西街44号",
        coordinate=Coordinate(latitude=39.9256, longitude=116.3963),
        poi_type="attraction",
        tags=["历史建筑", "自然风景"],
        suggested_duration_min=90,
        entry_tip="从南门进入，登万春亭看中轴线全景",
        open_note="06:30—21:00",
        operating_hours=OperatingHours(
            open_time="06:30",
            close_time="21:00",
            source_note="沿用项目已有开放时间基线，正式上线前需核对官方公告",
        ),
    ),
    "map:temple_of_heaven": MapPOI(
        poi_id="map:temple_of_heaven",
        canonical_name="天坛公园",
        address="北京市东城区天坛东里甲1号",
        coordinate=Coordinate(latitude=39.8822, longitude=116.4066),
        poi_type="attraction",
        tags=["历史建筑", "古建筑"],
        suggested_duration_min=150,
        entry_tip="从东门进入，先到祈年殿",
        open_note="06:00—21:00",
        operating_hours=OperatingHours(
            open_time="06:00",
            close_time="21:00",
            source_note="沿用项目已有开放时间基线，正式上线前需核对官方公告",
        ),
    ),
    "map:summer_palace": MapPOI(
        poi_id="map:summer_palace",
        canonical_name="颐和园",
        address="北京市海淀区新建宫门路19号",
        coordinate=Coordinate(latitude=39.9999, longitude=116.2755),
        poi_type="attraction",
        tags=["历史建筑", "自然风景"],
        suggested_duration_min=180,
        booking_reminder="建议提前购票",
        entry_tip="从东宫门进入，沿昆明湖游览",
    ),
    "map:badaling": MapPOI(
        poi_id="map:badaling",
        canonical_name="八达岭长城",
        address="北京市延庆区八达岭镇",
        coordinate=Coordinate(latitude=40.3590, longitude=116.0197),
        poi_type="attraction",
        tags=["历史建筑", "自然风景"],
        suggested_duration_min=300,
        booking_reminder="需预约，远郊建议全天",
        entry_tip="建议早出发，预留往返车程",
    ),
    "map:nanluoguxiang": MapPOI(
        poi_id="map:nanluoguxiang",
        canonical_name="南锣鼓巷",
        address="北京市东城区南锣鼓巷",
        coordinate=Coordinate(latitude=39.9375, longitude=116.4036),
        poi_type="attraction",
        tags=["胡同", "城市景观"],
        suggested_duration_min=90,
        entry_tip="从南口进入，向北步行游览",
    ),
    "map:shichahai": MapPOI(
        poi_id="map:shichahai",
        canonical_name="什刹海",
        address="北京市西城区什刹海",
        coordinate=Coordinate(latitude=39.9410, longitude=116.3826),
        poi_type="attraction",
        tags=["胡同", "自然风景", "城市夜景"],
        suggested_duration_min=120,
        entry_tip="从银锭桥开始，沿后海北岸走",
    ),
    "map:qianmen": MapPOI(
        poi_id="map:qianmen",
        canonical_name="前门大街",
        address="北京市东城区前门大街",
        coordinate=Coordinate(latitude=39.8995, longitude=116.3970),
        poi_type="area",
        tags=["商圈", "城市景观"],
        suggested_duration_min=60,
    ),
    "map:guomao": MapPOI(
        poi_id="map:guomao",
        canonical_name="国贸",
        address="北京市朝阳区建国门外大街",
        coordinate=Coordinate(latitude=39.9096, longitude=116.4545),
        poi_type="area",
        tags=["商圈", "城市夜景"],
        suggested_duration_min=60,
    ),
}

_ALIASES = {
    "故宫": "map:forbidden_city",
    "故宫博物院": "map:forbidden_city",
    "天安门": "map:tiananmen",
    "景山": "map:jingshan",
    "景山公园": "map:jingshan",
    "天坛": "map:temple_of_heaven",
    "天坛公园": "map:temple_of_heaven",
    "颐和园": "map:summer_palace",
    "长城": "map:badaling",
    "八达岭": "map:badaling",
    "八达岭长城": "map:badaling",
    "南锣鼓巷": "map:nanluoguxiang",
    "什刹海": "map:shichahai",
    "前门": "map:qianmen",
    "国贸": "map:guomao",
}


# 北京 30 景点主数据：为每个景点提供稳定 ID 和别名。AmapMapTool 仍会用
# 高德返回的真实中心坐标；这里的坐标只服务于离线 Mock 和 W1 校准。
_PHASE1_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "phase1_attractions.json"
_PHASE1_CATALOG = json.loads(_PHASE1_CATALOG_PATH.read_text(encoding="utf-8"))
PHASE1_ATTRACTIONS: tuple[dict, ...] = tuple(_PHASE1_CATALOG["attractions"])
for _item in PHASE1_ATTRACTIONS:
    _poi_id = _item["poi_id"]
    if _poi_id not in _MOCK_POIS:
        _MOCK_POIS[_poi_id] = MapPOI(
            poi_id=_poi_id,
            canonical_name=_item["canonical_name"],
            address="北京市（一期主数据中心点，正式使用以地图服务为准）",
            coordinate=Coordinate(
                latitude=_item["coordinate"]["latitude"],
                longitude=_item["coordinate"]["longitude"],
            ),
            poi_type=_item["poi_type"],
            tags=_item.get("tags", []),
        )
    for _alias in _item["aliases"]:
        _ALIASES[_alias] = _poi_id


class MockMapTool(MapTool):
    """Mock 地图工具：内置少量北京景点，路线基于直线距离估算（非真实数据）。"""

    def search_poi(self, name: str) -> Optional[MapPOI]:
        name = name.strip()
        poi_id = _ALIASES.get(name)
        if poi_id is None:
            # 模糊包含匹配
            for key, pid in _ALIASES.items():
                if key in name or name in key:
                    poi_id = pid
                    break
        return _MOCK_POIS.get(poi_id) if poi_id else None

    def get_poi(self, poi_id: str) -> Optional[MapPOI]:
        return _MOCK_POIS.get(poi_id)

    def get_route(
        self, origin_poi_id: str, destination_poi_id: str, transport_preferences: list[str]
    ) -> Optional[RouteQueryResult]:
        origin = self.get_poi(origin_poi_id)
        dest = self.get_poi(destination_poi_id)
        if origin is None or dest is None:
            return None
        km = _haversine_km(origin.coordinate, dest.coordinate)

        # 步行：按 5km/h
        walk_min = int(km / 5.0 * 60)
        # 公共交通：按 25km/h + 15 分钟等车换乘
        transit_min = int(km / 25.0 * 60 + 15)
        transfers = 0 if km < 5 else 1
        # 打车：按 35km/h + 10 分钟等车，起步 13 元 + 2.3 元/km
        drive_min = int(km / 35.0 * 60 + 10)
        cost = round(13 + 2.3 * km, 1)

        options = [
            ModeOption(
                mode="步行", duration_min=walk_min, distance_km=round(km, 2),
                walk_distance_m=int(km * 1000),
            ),
            ModeOption(
                mode="公共交通", duration_min=transit_min, distance_km=round(km, 2),
                cost_cny=3.0, transfers=transfers,
            ),
            ModeOption(
                mode="打车", duration_min=drive_min, distance_km=round(km, 2), cost_cny=cost,
            ),
        ]

        # 推荐策略（mock 启发式，非真实权重）
        if km < 1.5:
            mode, reason = "步行", f"两地相距约 {km:.1f} 公里，步行更直接"
        elif km > 25:
            mode = "打车"
            reason = f"距离较远（约 {km:.0f} 公里），打车节省时间"
        elif "少换乘" in transport_preferences:
            mode, reason = "打车", "用户偏好少换乘，打车更省心"
        elif "少走路" in transport_preferences:
            mode, reason = "打车", "用户偏好少走路，打车减少步行"
        else:
            mode = "公共交通"
            reason = f"距离约 {km:.1f} 公里，地铁相比打车费用更低且稳定"

        return RouteQueryResult(
            origin_poi_id=origin_poi_id,
            destination_poi_id=destination_poi_id,
            options=options,
            recommended_mode=mode,
            reason=reason,
        )

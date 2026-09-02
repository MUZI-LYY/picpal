"""高德地图工具：真实 POI 搜索、坐标与路线（GCJ-02）。

复用 map_tool 里的景点知识目录（名称/时长/预约/标签）作为静态知识库，
真实坐标与路线来自高德 Web 服务 API；内部 poi_id 保持稳定，
与出片点 RAG 的 poi_id 对齐。
"""
from __future__ import annotations

import time
from math import ceil
from typing import Optional

import httpx

from ..core.config import settings
from ..core.errors import AppError
from ..schemas.photo_spot import Coordinate
from .map_tool import (
    MapTool,
    MapPOI,
    ModeOption,
    RouteQueryResult,
    _ALIASES,
    _MOCK_POIS,
)

AMAP_BASE = "https://restapi.amap.com/v3"


def parse_location(location: str) -> Optional[Coordinate]:
    """高德 location 格式为 'lng,lat'（经度,纬度）。"""
    if not location:
        return None
    parts = location.split(",")
    if len(parts) != 2:
        return None
    try:
        lng, lat = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    return Coordinate(latitude=lat, longitude=lng, coordinate_system="GCJ-02")


def estimate_taxi_cny(distance_km: float) -> float:
    """北京出租车粗略估算：起步 13 元(3km) + 2.3 元/km。"""
    if distance_km <= 3:
        return 13.0
    return round(13 + 2.3 * (distance_km - 3), 1)


def _resolve_internal_id(name: str) -> Optional[str]:
    if name in _ALIASES:
        return _ALIASES[name]
    for key, pid in _ALIASES.items():
        if key in name or name in key:
            return pid
    return None


class AmapMapTool(MapTool):
    def __init__(self, api_key: Optional[str] = None, timeout: float = 10.0):
        self.api_key = api_key or settings.map_api_key
        self.timeout = timeout
        self._min_interval = 0.4  # 个人 Key QPS 低，限流
        self._last_call = 0.0
        self._cache: dict[str, MapPOI] = {}  # 内部 poi_id -> MapPOI（真实坐标）
        # 只缓存供应商返回的原始方案；推荐方式必须按每次请求的用户偏好重新计算。
        self._route_options_cache: dict[
            tuple[str, str], Optional[tuple[ModeOption, ...]]
        ] = {}

    def _throttle(self) -> None:
        now = time.monotonic()
        gap = now - self._last_call
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)
        self._last_call = time.monotonic()

    # ---------- HTTP ----------
    def _get(self, path: str, params: dict) -> dict:
        params = dict(params)
        params["key"] = self.api_key
        for attempt in range(3):
            self._throttle()
            try:
                resp = httpx.get(f"{AMAP_BASE}{path}", params=params, timeout=self.timeout)
            except httpx.HTTPError as exc:
                raise AppError("map_failed", "地图服务网络请求失败") from exc
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1":
                    return data
                info = data.get("info", "未知")
                if "CUQPS" in info or "LIMIT" in info:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise AppError("map_failed", f"地图服务错误：{info}")
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise AppError("map_failed", f"地图服务返回错误(HTTP {resp.status_code})")
        raise AppError("map_failed", "地图服务限流，请稍后重试")

    # ---------- 搜索 ----------
    def search_poi(self, name: str) -> Optional[MapPOI]:
        name = name.strip()
        internal_id = _resolve_internal_id(name)
        if internal_id:
            if internal_id in self._cache:
                return self._cache[internal_id]
            amap = self._amap_search(name)
            if amap is None:
                return None  # 高德确实无结果
            poi = self._build_poi(internal_id, amap)
            self._cache[internal_id] = poi
            return poi

        amap = self._amap_search(name)
        if amap is None:
            return None
        pid = f"amap:{amap.get('id', '')}"
        poi = self._build_poi(pid, amap)
        self._cache[pid] = poi
        return poi

    def get_poi(self, poi_id: str) -> Optional[MapPOI]:
        if poi_id in self._cache:
            return self._cache[poi_id]
        if poi_id.startswith("amap:"):
            amap = self._amap_detail(poi_id[5:])
            if amap is None:
                return None
            poi = self._build_poi(poi_id, amap)
            self._cache[poi_id] = poi
            return poi
        info = _MOCK_POIS.get(poi_id)
        if info:
            return self.search_poi(info.canonical_name)
        return None

    def _amap_search(self, name: str) -> Optional[dict]:
        data = self._get(
            "/place/text",
            {"keywords": name, "city": "北京", "citylimit": "true", "offset": 1},
        )
        pois = data.get("pois") or []
        return pois[0] if pois else None

    def search_raw(self, keyword: str, city: str = "北京", offset: int = 10) -> list[dict]:
        """原始搜索：返回高德 POI 列表（含 name/location/id），供准入管线唯一匹配用。"""
        data = self._get(
            "/place/text",
            {"keywords": keyword, "city": city, "citylimit": "true", "offset": offset},
        )
        return data.get("pois") or []

    def _amap_detail(self, amap_id: str) -> Optional[dict]:
        data = self._get("/place/detail", {"id": amap_id})
        pois = data.get("pois") or []
        return pois[0] if pois else None

    def _build_poi(self, poi_id: str, amap: dict) -> MapPOI:
        coord = parse_location(amap.get("location", ""))
        if coord is None:
            raise AppError("map_failed", "地图未返回有效坐标")
        info = _MOCK_POIS.get(poi_id)
        return MapPOI(
            poi_id=poi_id,
            canonical_name=(info.canonical_name if info else amap.get("name", poi_id)),
            address=amap.get("address") or "",
            coordinate=coord,
            map_source="amap",
            poi_type=(info.poi_type if info else "attraction"),
            tags=(info.tags if info else []),
            suggested_duration_min=(info.suggested_duration_min if info else 120),
            booking_reminder=(info.booking_reminder if info else None),
            entry_tip=(info.entry_tip if info else None),
            open_note=(info.open_note if info else None),
            operating_hours=(info.operating_hours if info else None),
        )

    # ---------- 路线 ----------
    def get_route(
        self, origin_poi_id: str, destination_poi_id: str, transport_preferences: list[str]
    ) -> Optional[RouteQueryResult]:
        key = (origin_poi_id, destination_poi_id)
        cached_options = self._route_options_cache.get(key)
        if key not in self._route_options_cache:
            o = self.get_poi(origin_poi_id)
            d = self.get_poi(destination_poi_id)
            if o is None or d is None:
                self._route_options_cache[key] = None
                return None

            origin = f"{o.coordinate.longitude},{o.coordinate.latitude}"
            dest = f"{d.coordinate.longitude},{d.coordinate.latitude}"

            options: list[ModeOption] = []
            walk = self._direction("walking", origin, dest)
            if walk and (walk["duration_min"] > 0 or walk["distance_km"] > 0):
                options.append(
                    ModeOption(
                        mode="步行", duration_min=walk["duration_min"], distance_km=walk["distance_km"],
                        walk_distance_m=walk.get("distance_m"),
                    )
                )
            transit = self._direction("transit", origin, dest)
            if transit and (transit["duration_min"] > 0 or transit["distance_km"] > 0):
                options.append(
                    ModeOption(
                        mode="公共交通", duration_min=transit["duration_min"], distance_km=transit["distance_km"],
                        cost_cny=3.0, transfers=None,
                    )
                )
            drive = self._direction("driving", origin, dest)
            if drive and (drive["duration_min"] > 0 or drive["distance_km"] > 0):
                options.append(
                    ModeOption(
                        mode="打车", duration_min=drive["duration_min"], distance_km=drive["distance_km"],
                        cost_cny=estimate_taxi_cny(drive["distance_km"]),
                    )
                )
            cached_options = tuple(options) if options else None
            self._route_options_cache[key] = cached_options

        if cached_options is None:
            return None
        options = [option.model_copy(deep=True) for option in cached_options]

        def _opt(mode: str) -> Optional[ModeOption]:
            return next((o for o in options if o.mode == mode), None)

        walk_opt = _opt("步行")
        drive_opt = _opt("打车")
        transit_opt = _opt("公共交通")

        if "少走路" in transport_preferences and drive_opt is not None:
            mode, reason = "打车", "用户偏好少走路，打车减少步行"
        elif walk_opt is not None and walk_opt.distance_km < 2.0:
            mode, reason = "步行", f"两地相距约 {walk_opt.distance_km:.1f} 公里，步行更直接"
        elif drive_opt is not None and drive_opt.distance_km > 25:
            mode, reason = "打车", f"距离较远（约 {drive_opt.distance_km:.0f} 公里），打车节省时间"
        elif "少换乘" in transport_preferences and drive_opt is not None:
            mode, reason = "打车", "用户偏好少换乘，打车更省心"
        elif "控制费用" in transport_preferences and transit_opt is not None:
            mode, reason = "公共交通", "用户偏好控制费用，公共交通成本更低"
        elif transit_opt is not None:
            mode, reason = "公共交通", f"距离约 {transit_opt.distance_km:.1f} 公里，地铁相比打车费用更低且稳定"
        elif drive_opt is not None:
            mode, reason = "打车", "打车较便捷"
        else:
            mode, reason = "步行", "步行即可到达"

        return RouteQueryResult(
            origin_poi_id=origin_poi_id,
            destination_poi_id=destination_poi_id,
            options=options,
            recommended_mode=mode,
            reason=reason,
        )

    def _direction(self, kind: str, origin: str, dest: str) -> Optional[dict]:
        """返回 {duration_min, distance_km, distance_m?}，失败返回 None（非关键路段降级）。"""
        if kind == "walking":
            path, extra = "/direction/walking", {}
        elif kind == "transit":
            path, extra = "/direction/transit/integrated", {"city": "北京"}
        else:
            path, extra = "/direction/driving", {}
        try:
            data = self._get(path, {"origin": origin, "destination": dest, **extra})
        except AppError:
            return None
        route = data.get("route") or {}
        if kind == "walking":
            p = (route.get("paths") or [{}])[0]
            return {
                "duration_min": ceil(int(p.get("duration", 0)) / 60),
                "distance_km": round(int(p.get("distance", 0)) / 1000, 2),
                "distance_m": int(p.get("distance", 0)),
            }
        if kind == "transit":
            t = (route.get("transits") or [{}])[0]
            return {
                "duration_min": ceil(int(t.get("duration", 0)) / 60),
                "distance_km": round(int(t.get("distance", 0)) / 1000, 2),
            }
        p = (route.get("paths") or [{}])[0]
        return {
            "duration_min": ceil(int(p.get("duration", 0)) / 60),
            "distance_km": round(int(p.get("distance", 0)) / 1000, 2),
        }

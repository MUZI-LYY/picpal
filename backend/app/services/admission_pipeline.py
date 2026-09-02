"""出片点数据采集与准入管线（采集侧，离线）。

原则：LLM 只提取候选证据；坐标判定、范围校验、准入判定均为确定性代码，
防止 LLM 编造坐标/位置。

该模块只处理离线采集数据，不在仓库中保存原始内容或凭证。
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ValidationError

from ..schemas.photo_spot import Coordinate
from .amap_tool import AmapMapTool, parse_location
from .llm_client import LLMClient
from .map_tool import MapPOI, PHASE1_ATTRACTIONS, _haversine_km

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# 范围阈值：子POI/定位标签距景点中心允许距离（公里），初始值，试点后调优
RANGE_KM = {
    "map:forbidden_city": 2.0,
    "map:temple_of_heaven": 2.0,
    "map:summer_palace": 3.0,
    "map:jingshan": 1.0,
    "map:badaling": 5.0,
}
DEFAULT_RANGE_KM = 2.0
CLUSTER_RADIUS_M = 150
DEDUP_RADIUS_M = 30  # 多源去重半径：同机位多源坐标几乎相同，30m 足以合并且不误并相邻机位
NAME_SIM_THRESHOLD = 0.8

_ALLOWED_PRECISION = {"exact_poi", "named_sub_poi"}
_PHASE1_RANGE_STATUS = {
    item["poi_id"]: item["range_review_status"] for item in PHASE1_ATTRACTIONS
}
_PHASE1_RANGE_KM = {item["poi_id"]: float(item["range_km"]) for item in PHASE1_ATTRACTIONS}

# 非北京城市名（常见旅游城市）：attraction 名含这些城市前缀/词时，判定为跨城市同名景点，拒绝。
# 北京同名景点误配是坐标风险源（如“珠海景山公园” vs 北京景山公园）。
_NON_BEIJING_CITIES = [
    "珠海", "上海", "广州", "深圳", "杭州", "成都", "重庆", "南京", "西安", "苏州",
    "天津", "青岛", "厦门", "长沙", "武汉", "郑州", "昆明", "大连", "三亚", "海口",
    "桂林", "丽江", "大理", "拉萨", "哈尔滨", "沈阳", "长春", "石家庄", "太原", "济南",
    "合肥", "南昌", "福州", "南宁", "贵阳", "兰州", "西宁", "银川", "呼和浩特", "乌鲁木齐",
    "香港", "澳门", "台北", "高雄", "新加坡", "东京", "首尔", "曼谷", "巴黎", "伦敦",
]


def is_beijing_attraction(name: str) -> bool:
    """判断景点名是否指向北京（不含非北京城市前缀/词）。"""
    if not name:
        return False
    return not any(city in name for city in _NON_BEIJING_CITIES)


# ---------- 纯函数（可离线单测） ----------
def name_similarity(q: str, name: str) -> float:
    if q == name:
        return 1.0
    if q and name and (q in name or name in q):
        return 0.9
    return 0.0


def is_exact_poi_match(q: str, name: str) -> bool:
    """判断 q 是否是 name 的精确核心名。

    - q == name 或 q 是 name 的子串（name 带"颐和园-"等前缀）→ 精确（q 是 POI 核心名）；
    - name 是 q 的子串（q 更长，含"下船处/对角线/北面"等修饰）→ 近似。

    例：is_exact("画中游", "颐和园-画中游") = True；is_exact("南湖岛下船处", "南湖岛") = False。
    """
    if q == name:
        return True
    if q and name and q in name:
        return True
    return False


def range_limit_km(poi_id: str) -> Optional[float]:
    """返回已获准自动使用的景点范围；一期未校准景点返回 None。"""
    if poi_id in _PHASE1_RANGE_STATUS and _PHASE1_RANGE_STATUS[poi_id] != "configured":
        return None
    if poi_id in _PHASE1_RANGE_KM:
        return _PHASE1_RANGE_KM[poi_id]
    return RANGE_KM.get(poi_id, DEFAULT_RANGE_KM)


def validate_geo_tag(coord: Coordinate, attraction: MapPOI) -> Optional[Coordinate]:
    """定位标签坐标：校验是否在景点合理范围。"""
    limit = range_limit_km(attraction.poi_id)
    if limit is None:
        return None
    if _haversine_km(coord, attraction.coordinate) <= limit:
        return coord
    return None


def cluster_center(coords: list[Coordinate]) -> Coordinate:
    lat = sum(c.latitude for c in coords) / len(coords)
    lon = sum(c.longitude for c in coords) / len(coords)
    return Coordinate(latitude=round(lat, 6), longitude=round(lon, 6), coordinate_system="GCJ-02")


def cluster_coords(
    coords: list[Coordinate], radius_m: int = CLUSTER_RADIUS_M
) -> list[list[Coordinate]]:
    """简单半径聚类：与簇内最近点的距离 < radius 则归入该簇（链式）。

    用"最近点"而非"首点"判断，避免链式距离（A-B 75m、B-C 90m、A-C 165m）被错误拆簇。
    """
    clusters: list[list[Coordinate]] = []
    for c in coords:
        for cl in clusters:
            if min(_haversine_km(c, other) * 1000 for other in cl) <= radius_m:
                cl.append(c)
                break
        else:
            clusters.append([c])
    return clusters


# ---------- LLM 提取结果的校验模型 ----------
class ExtractedSpotModel(BaseModel):
    spot_name: str
    location_description: str = ""
    location_precision: str = "fuzzy"
    photo_subjects: list[str] = []
    visual_styles: list[str] = []
    best_time: Optional[dict] = None


class NoteEvidenceModel(BaseModel):
    attraction: str
    level: str = "spot"
    has_explicit_location: bool = False
    sub_poi_names: list[str] = []
    spots: list[ExtractedSpotModel] = []


@dataclass
class AdmissionResult:
    status: str  # auto_verified / candidate / rejected
    attraction_poi_id: Optional[str] = None
    spot_name: Optional[str] = None
    coordinate: Optional[Coordinate] = None
    location_description: Optional[str] = None
    location_precision: Optional[str] = None
    photo_subjects: list[str] = field(default_factory=list)
    visual_styles: list[str] = field(default_factory=list)
    best_time: Optional[dict] = None
    admission_evidence: list[str] = field(default_factory=list)
    reason: str = ""


class AdmissionPipeline:
    def __init__(self, llm: Optional[LLMClient] = None, map_tool: Optional[AmapMapTool] = None):
        self.llm = llm or LLMClient()
        self.map_tool = map_tool or AmapMapTool()

    # ---------- 主入口 ----------
    def process_note(self, note: dict) -> AdmissionResult:
        """处理一篇采集到的笔记，返回第一个机位的准入结果（向后兼容）。

        一篇笔记含多个机位时，请用 process_note_all 逐个处理。
        note 字段（采集脚本产出）：text、geo{name,lng,lat}、source_url、author、images 等。
        """
        results = self.process_note_all(note)
        return results[0] if results else AdmissionResult(status="rejected", reason="无有效内容")

    def process_note_all(self, note: dict) -> list[AdmissionResult]:
        """处理一篇笔记，把其中每个机位拆成独立准入结果（一个机位一条）。

        对齐文档："一条出片点 = 一个最小知识单元，含多个机位必须拆分"。
        """
        evidence = self._extract_evidence(note.get("text", ""))
        # 跨城市同名景点拦截优先（如"珠海景山公园" vs 北京景山公园），不依赖机位提取结果。
        if evidence.attraction and not is_beijing_attraction(evidence.attraction):
            return [AdmissionResult(status="rejected", reason=f"非北京景点：{evidence.attraction}")]

        # 以"是否提取到具体机位"为准；level 是 LLM 的辅助判断，不可靠时以 spots 为准。
        spots = evidence.spots or []
        if not spots:
            return [AdmissionResult(status="candidate", reason="仅景点级位置，无具体机位")]

        attraction_poi = self._map_attraction(evidence.attraction)
        if attraction_poi is None:
            return [AdmissionResult(status="rejected", reason=f"景点无法识别：{evidence.attraction}")]

        results: list[AdmissionResult] = []
        for spot in spots:
            coord, evidence_used, is_exact = self._resolve_coordinate_for_spot(note, evidence, attraction_poi, spot)
            if coord is None:
                results.append(
                    AdmissionResult(
                        status="candidate",
                        attraction_poi_id=attraction_poi.poi_id,
                        spot_name=spot.spot_name,
                        location_description=spot.location_description,
                        reason="位置证据不足或无法唯一匹配",
                    )
                )
                continue
            if not is_exact:
                # 方位/设施/构图描述（如"万春亭北面""南湖岛下船处""对角线机位"）坐标是锚点附近，非精确点位。
                results.append(
                    AdmissionResult(
                        status="candidate",
                        attraction_poi_id=attraction_poi.poi_id,
                        spot_name=spot.spot_name,
                        location_description=spot.location_description,
                        reason="方位/近似描述，非精确机位点",
                    )
                )
                continue
            precision = spot.location_precision if spot.location_precision in _ALLOWED_PRECISION else "named_sub_poi"
            results.append(
                AdmissionResult(
                    status="auto_verified",
                    attraction_poi_id=attraction_poi.poi_id,
                    spot_name=spot.spot_name,
                    coordinate=coord,
                    location_description=spot.location_description,
                    location_precision=precision,
                    photo_subjects=spot.photo_subjects,
                    visual_styles=spot.visual_styles,
                    best_time=spot.best_time,
                    admission_evidence=evidence_used,
                    reason="ok",
                )
            )
        return results

    # ---------- LLM 提取 ----------
    def _extract_evidence(self, text: str) -> NoteEvidenceModel:
        system = (PROMPT_DIR / "extract_photo_spot.md").read_text(encoding="utf-8")
        user = json.dumps({"text": text}, ensure_ascii=False)
        for attempt in range(2):
            try:
                data = self.llm.complete_json(system, user)
                return NoteEvidenceModel.model_validate(data)
            except (ValidationError, Exception):
                if attempt == 0:
                    continue
                break
        # 兜底：无法提取时按"景点级"处理（进候选池，不上线）
        return NoteEvidenceModel(attraction="", level="attraction")

    # ---------- 景点映射 ----------
    def _map_attraction(self, name: str) -> Optional[MapPOI]:
        if not name:
            return None
        return self.map_tool.search_poi(name)

    # ---------- 坐标判定（确定性） ----------
    def _resolve_coordinate_for_spot(
        self, note: dict, evidence: NoteEvidenceModel, attraction: MapPOI, spot: ExtractedSpotModel
    ) -> tuple[Optional[Coordinate], list[str], bool]:
        # 返回 (coord, evidence_used, is_exact)；is_exact 表示坐标是否为精确命名子 POI 点位。
        # 优先级 1：定位标签/坐标（整篇级别，仅对单机位笔记有效；多机位时无法对应到具体机位）
        if len(evidence.spots) == 1:
            geo = note.get("geo")
            if geo:
                coord = parse_location(f"{geo.get('lng')},{geo.get('lat')}" if "lng" in geo else geo.get("location", ""))
                if coord and validate_geo_tag(coord, attraction):
                    return coord, ["geo_tag_in_range"], True

        # 优先级 2：机位名本身唯一匹配（只用当前机位自身信息，避免跨机位串位）
        if spot.spot_name:
            coord, is_exact = self._unique_match_sub_poi(spot.spot_name, attraction)
            if coord:
                return coord, ["explicit_location", "map_unique_match"], is_exact

        # 优先级 3：明确位置表达 → 抽子POI词 → 唯一匹配（描述抽取的可能是拍摄对象，非站立位置）
        if evidence.has_explicit_location and spot.location_description:
            for name in self._searchable_poi_names(spot.location_description):
                coord, _ = self._unique_match_sub_poi(name, attraction)
                if coord:
                    return coord, ["explicit_location", "map_unique_match"], False

        return None, [], False

    def _unique_match_sub_poi(self, name: str, attraction: MapPOI) -> tuple[Optional[Coordinate], bool]:
        """子 POI 坐标判定：名称相似 → 范围过滤 → 范围内唯一/坐标聚集。

        返回 (coord, is_exact)：is_exact 表示 name 是否为 POI 的核心名（精确匹配），
        用于区分"太和门"（精确）与"南湖岛下船处"（近似锚点）。
        """
        if not name:
            return None, False
        results = self.map_tool.search_raw(name, city="北京", offset=10)
        # 精确相等优先：存在 name == POI名 的候选时，只用精确相等的，
        # 忽略包含匹配的干扰项（如搜"知春亭"时高德返回的"知春亭茶饮"奶茶店）。
        exact = [p for p in results if (p.get("name", "") or "").strip() == name.strip()]
        if exact:
            candidates = exact
        else:
            candidates = [p for p in results if name_similarity(name, p.get("name", "")) >= NAME_SIM_THRESHOLD]

        limit = range_limit_km(attraction.poi_id)
        if limit is None:
            return None, False
        in_range: list[tuple[Coordinate, bool]] = []
        for p in candidates:
            coord = parse_location(p.get("location", ""))
            if coord is None:
                continue
            if _haversine_km(coord, attraction.coordinate) <= limit:
                in_range.append((coord, is_exact_poi_match(name, p.get("name", ""))))

        if not in_range:
            return None, False
        coords = [c for c, _ in in_range]
        is_exact = any(e for _, e in in_range)
        if len(coords) == 1:
            return coords[0], is_exact
        clusters = cluster_coords(coords, radius_m=CLUSTER_RADIUS_M)
        if len(clusters) == 1:
            return cluster_center(coords), is_exact
        # 多簇：若最近簇明显更近（<1km 且与次近簇差 >1.5km），取最近簇；
        # 否则多义（如涵虚堂 vs 涵虚 两处都近），放弃。
        def _nearest_dist(cl: list[Coordinate]) -> float:
            return min(_haversine_km(c, attraction.coordinate) for c in cl)

        ordered = sorted(clusters, key=_nearest_dist)
        nearest = _nearest_dist(ordered[0])
        second = _nearest_dist(ordered[1])
        if nearest < 1.0 and (second - nearest) > 1.5:
            return cluster_center(ordered[0]), is_exact
        return None, False

    def _searchable_poi_names(self, location_description: str) -> list[str]:
        """从位置描述中提取可搜索的地点词（复用 LLM 简化抽取）。"""
        if not location_description:
            return []
        system = (PROMPT_DIR / "extract_photo_spot.md").read_text(encoding="utf-8")
        user = json.dumps({"task": "只抽取位置描述中可在地图上搜索到的地点名，输出 JSON {\"names\":[...] }", "text": location_description}, ensure_ascii=False)
        try:
            data = self.llm.complete_json(system, user)
            names = data.get("names") or []
            return [str(n) for n in names if n]
        except Exception:
            return []


# ---------- 环节 5：多源去重（纯函数，可离线单测） ----------
def _merge_str_list(cluster: list[dict], key: str) -> list:
    out: list = []
    for r in cluster:
        for v in (r.get(key) or []):
            if v and v not in out:
                out.append(v)
    return out


def _merge_photos(cluster: list[dict]) -> list:
    out: list = []
    seen: set = set()
    for r in cluster:
        for p in (r.get("reference_photos") or []):
            url = p.get("storage_url", "")
            if url and url not in seen:
                seen.add(url)
                out.append(p)
    return out


def _merge_sources(cluster: list[dict]) -> list:
    out: list = []
    seen: set = set()
    for r in cluster:
        for s in (r.get("source_refs") or []):
            sid = s.get("source_id", "")
            if sid and sid not in seen:
                seen.add(sid)
                out.append(s)
    return out


def _merge_cluster(cluster: list[dict]) -> dict:
    """把同一机位的一簇重复记录合并为一条。"""
    if len(cluster) == 1:
        return cluster[0]

    coords = [Coordinate(**r["coordinate"]) for r in cluster]
    center = cluster_center(coords)
    name = Counter(r["spot_name"] for r in cluster).most_common(1)[0][0]

    descs: list[str] = []
    for r in cluster:
        d = (r.get("location_description") or "").strip()
        if d and d not in descs:
            descs.append(d)

    # 多源是强证据：只按去重后的独立 source_id 计数，重复行不能抬高置信度。
    confidence = max(float(r.get("confidence", 0.6)) for r in cluster)
    unique_source_ids = {
        source.get("source_id")
        for record in cluster
        for source in (record.get("source_refs") or [])
        if source.get("source_id")
    }
    confidence = min(0.95, confidence + 0.1 * max(0, len(unique_source_ids) - 1))

    merged = dict(cluster[0])
    merged.update(
        {
            "spot_id": f"spot:{cluster[0]['poi_id']}:dedup:{name}",
            "spot_name": name,
            "coordinate": center.model_dump(),
            "location_description": "；".join(descs),
            "photo_subjects": _merge_str_list(cluster, "photo_subjects"),
            "visual_styles": _merge_str_list(cluster, "visual_styles"),
            "reference_photos": _merge_photos(cluster),
            "source_refs": _merge_sources(cluster),
            "admission_evidence": _merge_str_list(cluster, "admission_evidence"),
            "confidence": round(confidence, 2),
        }
    )
    return merged


def dedup_photo_spots(records: list[dict], radius_m: int = DEDUP_RADIUS_M) -> list[dict]:
    """环节 5：多源去重。

    同一 poi 下、坐标聚集（簇中心距 < radius_m）的记录视为同一机位，合并为一条：
    坐标取聚类中心、名称取出现最多的、多源置信度递增。
    半径独立于 CLUSTER_RADIUS_M（坐标判定聚类），更小以免误并相邻不同机位。
    """
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["poi_id"], []).append(r)

    out: list[dict] = []
    for _poi_id, recs in groups.items():
        clusters: list[list[dict]] = []
        for r in recs:
            coord = Coordinate(**r["coordinate"])
            placed = False
            for cl in clusters:
                cl_center = cluster_center([Coordinate(**x["coordinate"]) for x in cl])
                if _haversine_km(coord, cl_center) * 1000 <= radius_m:
                    cl.append(r)
                    placed = True
                    break
            if not placed:
                clusters.append([r])
        for cl in clusters:
            out.append(_merge_cluster(cl))
    return out

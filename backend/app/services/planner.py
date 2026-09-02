"""规划编排服务：串起解析、地图、出片点检索、住宿推荐与确定性校验。

固定业务流程由代码状态机编排（手册第九节第 3 条）。
LLM 只负责解析与候选编排（天数/顺序/主题），
精确路线、出片点、来源、时间轴由本服务确定性回填后再校验。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..core import store
from ..core.errors import AppError
from ..core.store import TripStore
from ..core.timeutil import add_minutes, to_minutes
from ..schemas import (
    ParsedTripRequest,
    ItineraryPlan,
    ItineraryDay,
    ItineraryItem,
    RouteSegment,
    LodgingRecommendation,
    ValidationCheck,
)
from .map_tool import MapTool, MapPOI, RouteQueryResult, _haversine_km
from .model_adapter import ModelAdapter, TripCandidate, CandidateDay
from .photo_spot_retriever import PhotoSpotRetriever
from .validator import Validator

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "app" / "schemas" / "json_schemas"

# 默认补充景点（mock；真实版由景点候选服务返回）
_DEFAULT_POI_IDS = [
    "map:forbidden_city",
    "map:tiananmen",
    "map:jingshan",
    "map:temple_of_heaven",
    "map:summer_palace",
    "map:shichahai",
    "map:nanluoguxiang",
    "map:badaling",
]

_AREA_POI_IDS = ["map:qianmen", "map:guomao", "map:shichahai"]


def _target_attraction_count(days: int) -> int:
    return min(3 + 2 * (days - 1), 9)


class Planner:
    def __init__(
        self,
        model: ModelAdapter,
        map_tool: MapTool,
        retriever: PhotoSpotRetriever,
        validator: Validator,
        store_: TripStore = store.store,
    ):
        self.model = model
        self.map_tool = map_tool
        self.retriever = retriever
        self.validator = validator
        self.store = store_

    # ---------- 对外入口 ----------
    def start(self, task_id: str, input_text: str, input_fields: dict) -> None:
        t = threading.Thread(target=self._run, args=(task_id, input_text, input_fields), daemon=True)
        t.start()

    def _run(self, task_id: str, input_text: str, input_fields: dict) -> None:
        try:
            self._execute(task_id, input_text, input_fields)
        except AppError as exc:
            self.store.update(task_id, status=exc.code, error=exc.message)
        except Exception as exc:  # noqa: BLE001 兜底，不向用户泄露堆栈
            self.store.update(task_id, status="planning_failed", error="生成失败，请稍后重试")

    # ---------- 同步核心：供 RunOrchestrator 复用 ----------
    def generate(
        self,
        parsed: ParsedTripRequest,
        *,
        stage_callback=None,
    ) -> ItineraryPlan:
        """同步执行规划业务，并通过 stage_callback(key) 报告真实阶段。"""
        cb = stage_callback or (lambda key: None)

        cb("understanding_request")

        cb("resolving_pois")
        pois = self._resolve_pois(parsed)
        lodging_poi = self._resolve_lodging(parsed)

        cb("planning_routes")
        route_context = self._route_context(pois, parsed.transport_preferences, lodging_poi)
        lodging = self._recommend_lodging(pois, parsed, lodging_poi)
        candidate = self.model.plan_itinerary(
            parsed, pois, route_context, [l.model_dump() for l in lodging]
        )
        candidate = self._normalize_candidate(candidate, pois, parsed.days)
        candidate = self._avoid_closed_days(candidate, pois, parsed.start_date)

        cb("recommending_lodging")

        cb("retrieving_photo_spots")
        photo_hits = {
            poi.poi_id: self.retriever.retrieve(
                request_id=parsed.request_id,
                poi_id=poi.poi_id,
                photo_preferences=parsed.photo_preferences,
                visit_date=(parsed.start_date.isoformat() if parsed.start_date else None),
                arrival_time="09:00",
                limit=3,
            )
            for poi in pois
        }

        draft = self._assemble_plan(parsed, candidate, pois, lodging, photo_hits, lodging_poi)

        cb("validating")
        return self._finalize_plan(draft, pois, photo_hits)

    def _execute(self, task_id: str, input_text: str, input_fields: dict) -> None:
        # 1. 解析
        parsed = self.model.parse_request(input_text, input_fields)
        self.store.set_stage(task_id, "planning")
        self.store.update(task_id, parsed_request=parsed.model_dump(mode="json"))

        # 2. 景点标准化（地图）
        pois = self._resolve_pois(parsed)
        lodging_poi = self._resolve_lodging(parsed)
        self.store.update(task_id, parsed_request=parsed.model_dump(mode="json"))

        # 3. 路线上下文（供模型编排参考）
        route_context = self._route_context(pois, parsed.transport_preferences, lodging_poi)

        # 4. 住宿推荐（确定性）
        lodging = self._recommend_lodging(pois, parsed, lodging_poi)

        # 5. 出片点检索
        self.store.set_stage(task_id, "retrieving_photo_spots")
        photo_hits = {
            poi.poi_id: self.retriever.retrieve(
                request_id=parsed.request_id,
                poi_id=poi.poi_id,
                photo_preferences=parsed.photo_preferences,
                visit_date=(parsed.start_date.isoformat() if parsed.start_date else None),
                arrival_time="09:00",
                limit=3,
            )
            for poi in pois
        }

        # 6. 模型生成候选编排（只决定天数/顺序/主题）
        candidate = self.model.plan_itinerary(
            parsed, pois, route_context, [l.model_dump() for l in lodging]
        )
        candidate = self._normalize_candidate(candidate, pois, parsed.days)
        candidate = self._avoid_closed_days(candidate, pois, parsed.start_date)

        # 7. 确定性回填：时间轴 + 路线 + 出片点
        draft = self._assemble_plan(parsed, candidate, pois, lodging, photo_hits, lodging_poi)
        self.store.set_stage(task_id, "draft")
        self.store.update(task_id, plan=draft.model_dump(mode="json"))

        # 8. 确定性校验
        self.store.set_stage(task_id, "validating")
        self._validate_and_finalize(task_id, draft, pois, photo_hits)

    # ---------- 景点标准化 ----------
    def _resolve_pois(self, parsed: ParsedTripRequest) -> list[MapPOI]:
        pois: list[MapPOI] = []
        seen: set[str] = set()
        excluded: set[str] = set()
        for name in parsed.must_exclude:
            poi = self.map_tool.search_poi(name)
            if poi is not None:
                excluded.add(poi.poi_id)

        for name in parsed.must_include:
            poi = self.map_tool.search_poi(name)
            if poi is None:
                raise AppError("map_failed", f"必去景点无法识别：{name}", http_status=422)
            if poi.poi_id not in excluded and poi.poi_id not in seen:
                pois.append(poi)
                seen.add(poi.poi_id)

        target = _target_attraction_count(parsed.days)
        for pid in _DEFAULT_POI_IDS:
            if len(pois) >= target:
                break
            if pid in excluded:
                continue
            poi = self.map_tool.get_poi(pid)
            if poi and poi.poi_id not in excluded and poi.poi_id not in seen:
                pois.append(poi)
                seen.add(poi.poi_id)

        if not pois:
            raise AppError("map_failed", "未匹配到可规划的北京景点")
        return pois

    def _resolve_lodging(self, parsed: ParsedTripRequest) -> Optional[MapPOI]:
        if parsed.lodging_input is None:
            return None
        poi = self.map_tool.search_poi(parsed.lodging_input.raw_text)
        if poi is None:
            parsed.lodging_input.poi_id = None
            parsed.lodging_input.matched_name = None
            parsed.assumptions.append(
                f"未能识别住宿位置“{parsed.lodging_input.raw_text}”，本次按推荐住宿区域估算路线"
            )
            return None
        parsed.lodging_input.poi_id = poi.poi_id
        parsed.lodging_input.matched_name = poi.canonical_name
        return poi

    # ---------- 路线上下文（模型编排用的粗略距离估算，非展示数据）----------
    def _route_context(
        self,
        pois: list[MapPOI],
        prefs: list[str],
        lodging_poi: Optional[MapPOI] = None,
    ) -> list[dict]:
        ctx: list[dict] = []
        if lodging_poi is not None:
            for poi in pois:
                km = _haversine_km(lodging_poi.coordinate, poi.coordinate)
                ctx.append(
                    {
                        "from": lodging_poi.poi_id,
                        "from_name": lodging_poi.canonical_name,
                        "to": poi.poi_id,
                        "to_name": poi.canonical_name,
                        "straight_km": round(km, 1),
                        "est_transit_min": int(km / 25.0 * 60 + 15),
                        "est_drive_min": int(km / 35.0 * 60 + 10),
                        "lodging_origin": True,
                    }
                )
        for i in range(len(pois)):
            for j in range(i + 1, len(pois)):
                km = _haversine_km(pois[i].coordinate, pois[j].coordinate)
                ctx.append(
                    {
                        "from": pois[i].poi_id,
                        "from_name": pois[i].canonical_name,
                        "to": pois[j].poi_id,
                        "to_name": pois[j].canonical_name,
                        "straight_km": round(km, 1),
                        "est_transit_min": int(km / 25.0 * 60 + 15),
                        "est_drive_min": int(km / 35.0 * 60 + 10),
                    }
                )
        return ctx

    # ---------- 住宿推荐（确定性：选质心最近的商圈）----------
    def _recommend_lodging(
        self,
        pois: list[MapPOI],
        parsed: ParsedTripRequest,
        lodging_poi: Optional[MapPOI] = None,
    ) -> list[LodgingRecommendation]:
        if not pois:
            return []
        lat = sum(p.coordinate.latitude for p in pois) / len(pois)
        lon = sum(p.coordinate.longitude for p in pois) / len(pois)
        from ..schemas.photo_spot import Coordinate

        centroid = Coordinate(latitude=lat, longitude=lon)
        areas = [self.map_tool.get_poi(pid) for pid in _AREA_POI_IDS]
        areas = [a for a in areas if a is not None]
        areas.sort(key=lambda a: _haversine_km(centroid, a.coordinate))

        result: list[LodgingRecommendation] = []
        if lodging_poi is not None:
            avg_min = int(
                sum(_haversine_km(lodging_poi.coordinate, p.coordinate) for p in pois)
                / len(pois)
                / 25.0
                * 60
            )
            verdict = "适合本次行程" if avg_min <= 40 else "通勤成本偏高"
            result.append(
                LodgingRecommendation(
                    area_id=lodging_poi.poi_id,
                    name=lodging_poi.canonical_name,
                    level="当前住宿评估",
                    reason=f"当前住宿{verdict}，到主要景点平均约 {avg_min} 分钟",
                    covered_attractions=[p.canonical_name for p in pois],
                    avg_transit_min=avg_min,
                )
            )

        recommendation_areas = [
            area for area in areas if lodging_poi is None or area.poi_id != lodging_poi.poi_id
        ][:2]
        for rank, area in enumerate(recommendation_areas):
            avg_min = int(
                sum(_haversine_km(area.coordinate, p.coordinate) for p in pois) / len(pois) / 25.0 * 60
            )
            level = "首选" if rank == 0 else "备选"
            result.append(
                LodgingRecommendation(
                    area_id=area.poi_id,
                    name=area.canonical_name,
                    level=level,
                    representative_station=f"{area.canonical_name}地铁站",
                    reason=f"位于景点分布中心，到主要景点平均约 {avg_min} 分钟",
                    covered_attractions=[p.canonical_name for p in pois],
                    avg_transit_min=avg_min,
                )
            )
        return result

    # ---------- 候选归一化（保证每个景点恰好分配一次、天数合规）----------
    def _normalize_candidate(
        self, candidate: TripCandidate, pois: list[MapPOI], n_days: int
    ) -> TripCandidate:
        known = {p.poi_id for p in pois}
        assigned: set[str] = set()
        days: list[CandidateDay] = []
        for cd in candidate.days[:n_days]:
            poi_ids = []
            for pid in cd.poi_ids:
                if pid in known and pid not in assigned:
                    poi_ids.append(pid)
                    assigned.add(pid)
            if poi_ids:
                days.append(CandidateDay(theme=cd.theme, poi_ids=poi_ids))

        remaining = [p.poi_id for p in pois if p.poi_id not in assigned]
        if remaining:
            if days:
                days[-1].poi_ids.extend(remaining)
            else:
                days.append(CandidateDay(poi_ids=remaining))

        if not days:
            raise AppError("planning_failed", "未能形成有效行程")
        return TripCandidate(title=candidate.title, overview=candidate.overview, days=days)

    @staticmethod
    def _is_closed_on(poi: MapPOI, visit_date) -> bool:
        hours = poi.operating_hours
        return bool(hours and visit_date.weekday() in hours.closed_weekdays)

    def _avoid_closed_days(
        self,
        candidate: TripCandidate,
        pois: list[MapPOI],
        start_date,
    ) -> TripCandidate:
        """可换日时交换景点，无法消除的闭馆冲突交给校验器硬失败。"""
        if start_date is None or len(candidate.days) < 2:
            return candidate
        pois_by_id = {poi.poi_id: poi for poi in pois}

        for source_index, source_day in enumerate(candidate.days):
            source_date = start_date + timedelta(days=source_index)
            for source_pos, source_id in enumerate(list(source_day.poi_ids)):
                source_poi = pois_by_id.get(source_id)
                if source_poi is None or not self._is_closed_on(source_poi, source_date):
                    continue

                swapped = False
                for target_index, target_day in enumerate(candidate.days):
                    if target_index == source_index:
                        continue
                    target_date = start_date + timedelta(days=target_index)
                    if self._is_closed_on(source_poi, target_date):
                        continue
                    for target_pos, target_id in enumerate(target_day.poi_ids):
                        target_poi = pois_by_id.get(target_id)
                        if target_poi is None or self._is_closed_on(target_poi, source_date):
                            continue
                        source_day.poi_ids[source_pos], target_day.poi_ids[target_pos] = (
                            target_id,
                            source_id,
                        )
                        swapped = True
                        break
                    if swapped:
                        break
        return candidate

    # ---------- 确定性回填：时间轴 + 路线 + 出片点 ----------
    def _assemble_plan(
        self,
        parsed: ParsedTripRequest,
        candidate: TripCandidate,
        pois: list[MapPOI],
        lodging: list[LodgingRecommendation],
        photo_hits: dict,
        lodging_poi: Optional[MapPOI] = None,
    ) -> ItineraryPlan:
        pois_by_id = {p.poi_id: p for p in pois}
        window_start = parsed.daily_time_window.start if parsed.daily_time_window else "09:00"
        window_end = parsed.daily_time_window.end if parsed.daily_time_window else "20:00"

        days: list[ItineraryDay] = []
        for idx, cd in enumerate(candidate.days, start=1):
            date = (parsed.start_date + timedelta(days=idx - 1)).isoformat() if parsed.start_date else None
            items: list[ItineraryItem] = []
            current = window_start
            prev_poi_id: Optional[str] = lodging_poi.poi_id if lodging_poi else None
            for j, pid in enumerate(cd.poi_ids):
                poi = pois_by_id.get(pid)
                if poi is None:
                    continue
                route_from_prev = None
                if prev_poi_id is not None:
                    rq = self.map_tool.get_route(prev_poi_id, pid, parsed.transport_preferences)
                    if rq:
                        route_from_prev = self._to_route_segment(rq)
                        current = add_minutes(current, route_from_prev.duration_min)
                if poi.operating_hours and to_minutes(current) < to_minutes(
                    poi.operating_hours.open_time
                ):
                    current = poi.operating_hours.open_time
                start = current
                end = add_minutes(start, poi.suggested_duration_min)
                hit = photo_hits.get(pid)
                spots = list(hit.hits) if hit else []
                items.append(
                    ItineraryItem(
                        item_id=f"d{idx}-i{j + 1}",
                        poi={
                            "poi_id": poi.poi_id,
                            "canonical_name": poi.canonical_name,
                            "map_source": poi.map_source,
                        },
                        start_time=start,
                        end_time=end,
                        stay_duration_min=poi.suggested_duration_min,
                        booking_reminder=poi.booking_reminder,
                        entry_tip=poi.entry_tip,
                        route_from_previous=route_from_prev,
                        photo_spots=spots,
                    )
                )
                prev_poi_id = pid
                current = end
            days.append(
                ItineraryDay(
                    day_index=idx,
                    date=date,
                    theme=cd.theme,
                    start_time=window_start,
                    end_time=window_end,
                    items=items,
                )
            )

        return ItineraryPlan(
            plan_id=f"plan:{parsed.request_id.replace('req:', 'req-')}:v1",
            request_id=parsed.request_id,
            status="draft",
            title=candidate.title,
            overview=candidate.overview,
            request_summary={"days": parsed.days, "companions": parsed.companion_types, "pace": parsed.pace},
            lodging_recommendations=lodging,
            days=days,
            limitations=[],
            planner={"model": self.model.model_label, "model_version": "0.1.0", "prompt_version": "planner-v1.1"},
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _to_route_segment(rq: RouteQueryResult) -> Optional[RouteSegment]:
        opt = next((o for o in rq.options if o.mode == rq.recommended_mode), None)
        if opt is None:
            opt = rq.options[0] if rq.options else None
        if opt is None:
            return None
        return RouteSegment(
            origin_poi_id=rq.origin_poi_id,
            destination_poi_id=rq.destination_poi_id,
            recommended_mode=rq.recommended_mode,  # type: ignore[arg-type]
            duration_min=opt.duration_min,
            distance_km=opt.distance_km,
            cost_cny=opt.cost_cny,
            walk_distance_m=opt.walk_distance_m,
            transfers=opt.transfers,
            reason=rq.reason,
        )

    # ---------- 校验与状态转换 ----------
    def _finalize_plan(
        self,
        plan: ItineraryPlan,
        pois: list[MapPOI],
        photo_hits: dict,
    ) -> ItineraryPlan:
        map_pois = {p.poi_id: p for p in pois}
        map_poi_ids = set(map_pois)
        checks = self._run_checks(plan, map_poi_ids, photo_hits, map_pois)

        plan, removed = self._apply_spot_fixes(plan, checks)
        checks = self._run_checks(plan, map_poi_ids, photo_hits, map_pois)
        if removed:
            checks.append(
                ValidationCheck(
                    code="invalid_photo_spot", severity="warning",
                    message=f"已移除 {removed} 个无效出片点，不影响主行程",
                )
            )

        has_fail = any(c.severity == "fail" for c in checks)
        status = "failed" if has_fail else "validated"
        validation_status = "fail" if has_fail else "pass"

        plan.status = status  # type: ignore[assignment]
        plan.validation.status = validation_status  # type: ignore[assignment]
        plan.validation.checks = checks
        plan.validation.checked_at = datetime.now(timezone.utc)
        return plan

    def _validate_and_finalize(
        self,
        task_id: str,
        plan: ItineraryPlan,
        pois: list[MapPOI],
        photo_hits: dict,
    ) -> None:
        plan = self._finalize_plan(plan, pois, photo_hits)
        self.store.set_stage(task_id, plan.status)
        self.store.update(task_id, plan=plan.model_dump(mode="json"))

    def _run_checks(self, plan, map_poi_ids, photo_hits, map_pois=None) -> list[ValidationCheck]:
        checks: list[ValidationCheck] = []
        schema_errors = self._schema_check(plan)
        for e in schema_errors:
            checks.append(ValidationCheck(code="invalid_schema", severity="fail", message=e))
        checks.extend(
            self.validator.validate(plan, map_poi_ids, photo_hits, map_pois=map_pois)
        )
        return checks

    def _schema_check(self, plan: ItineraryPlan) -> list[str]:
        schema_path = SCHEMA_DIR / "itinerary_plan.schema.json"
        if not schema_path.exists():
            return []
        import jsonschema

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = []
        for err in jsonschema.Draft202012Validator(schema).iter_errors(plan.model_dump(mode="json")):
            errors.append(f"{'/'.join(str(p) for p in err.path) or '$'}: {err.message}")
        return errors[:5]

    def _apply_spot_fixes(self, plan: ItineraryPlan, checks: list[ValidationCheck]) -> tuple[ItineraryPlan, int]:
        drop_best_time: set[str] = set()
        drop_spot: set[str] = set()
        for c in checks:
            if c.severity != "spot_fail" or not c.spot_id:
                continue
            if c.code == "unsupported_best_time":
                drop_best_time.add(c.spot_id)
            else:
                drop_spot.add(c.spot_id)

        removed = 0
        for day in plan.days:
            for item in day.items:
                kept = []
                for spot in item.photo_spots:
                    if spot.spot_id in drop_spot:
                        removed += 1
                        continue
                    if spot.spot_id in drop_best_time and spot.best_time is not None:
                        spot.best_time = None
                    kept.append(spot)
                item.photo_spots = kept
        return plan, removed

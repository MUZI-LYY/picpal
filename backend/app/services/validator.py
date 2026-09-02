"""确定性校验器：负责 draft → validated / failed 状态判断。

本模块只负责生成校验结果；状态转换与出片点修复由 planner 执行。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from ..core.timeutil import to_minutes
from ..schemas import ItineraryPlan, PhotoSpotRetrievalHit, ValidationCheck


class Validator:
    def validate(
        self,
        plan: ItineraryPlan,
        map_poi_ids: set[str],
        photo_hits: dict[str, PhotoSpotRetrievalHit],
        map_pois: Optional[dict[str, Any]] = None,
    ) -> list[ValidationCheck]:
        checks: list[ValidationCheck] = []

        # 2. missing_map_poi
        for day in plan.days:
            for item in day.items:
                if item.poi.poi_id not in map_poi_ids:
                    checks.append(
                        ValidationCheck(
                            code="missing_map_poi", severity="fail",
                            message=f"景点 {item.poi.canonical_name} 缺少地图 POI 记录",
                            day_index=day.day_index, item_id=item.item_id,
                        )
                    )

        # 3. 开放时间与闭馆日
        if map_pois is not None:
            for day in plan.days:
                visit_date = None
                if day.date:
                    try:
                        visit_date = date.fromisoformat(day.date)
                    except ValueError:
                        visit_date = None
                for item in day.items:
                    poi = map_pois.get(item.poi.poi_id)
                    if poi is None:
                        continue
                    hours = getattr(poi, "operating_hours", None)
                    if hours is None:
                        checks.append(
                            ValidationCheck(
                                code="unknown_open_hours",
                                severity="warning",
                                message=f"{item.poi.canonical_name} 缺少可靠开放时间，请出行前确认",
                                day_index=day.day_index,
                                item_id=item.item_id,
                            )
                        )
                        continue
                    if visit_date and visit_date.weekday() in hours.closed_weekdays:
                        checks.append(
                            ValidationCheck(
                                code="closed_day_conflict",
                                severity="fail",
                                message=f"{item.poi.canonical_name} 在 {day.date} 闭馆",
                                day_index=day.day_index,
                                item_id=item.item_id,
                            )
                        )
                        continue
                    if item.start_time and item.end_time:
                        start = to_minutes(item.start_time)
                        end = to_minutes(item.end_time)
                        opens = to_minutes(hours.open_time)
                        closes = to_minutes(hours.close_time)
                        if start < opens or end > closes:
                            checks.append(
                                ValidationCheck(
                                    code="outside_open_hours",
                                    severity="fail",
                                    message=(
                                        f"{item.poi.canonical_name} 安排为 {item.start_time}—{item.end_time}，"
                                        f"超出常规开放时间 {hours.open_time}—{hours.close_time}"
                                    ),
                                    day_index=day.day_index,
                                    item_id=item.item_id,
                                )
                            )

        # 4. duplicate_poi
        seen: dict[str, list[str]] = {}
        for day in plan.days:
            for item in day.items:
                seen.setdefault(item.poi.poi_id, []).append(item.item_id)
        for poi_id, ids in seen.items():
            if len(ids) > 1:
                checks.append(
                    ValidationCheck(
                        code="duplicate_poi", severity="warning",
                        message=f"景点 {poi_id} 被重复安排（{len(ids)} 次）",
                    )
                )

        # 4. time_conflict
        for day in plan.days:
            prev_end: Optional[int] = None
            for item in day.items:
                if item.start_time and item.end_time:
                    s, e = to_minutes(item.start_time), to_minutes(item.end_time)
                    if s >= e:
                        checks.append(
                            ValidationCheck(
                                code="time_conflict", severity="fail",
                                message=f"第{day.day_index}天 {item.poi.canonical_name} 开始时间不早于结束时间",
                                day_index=day.day_index, item_id=item.item_id,
                            )
                        )
                    if prev_end is not None and s < prev_end:
                        checks.append(
                            ValidationCheck(
                                code="time_conflict", severity="fail",
                                message=f"第{day.day_index}天 {item.poi.canonical_name} 与上一景点时间重叠",
                                day_index=day.day_index, item_id=item.item_id,
                            )
                        )
                    prev_end = e

        # 5. excessive_density
        for day in plan.days:
            if len(day.items) > 5:
                checks.append(
                    ValidationCheck(
                        code="excessive_density", severity="fail",
                        message=f"第{day.day_index}天主要景点超过 5 个（{len(day.items)} 个）",
                        day_index=day.day_index,
                    )
                )

        # 6. unreasonable_route（明显折返/跨区成本过高）
        for day in plan.days:
            for item in day.items:
                r = item.route_from_previous
                if r and r.distance_km > 30:
                    checks.append(
                        ValidationCheck(
                            code="unreasonable_route", severity="warning",
                            message=f"第{day.day_index}天路段距离约 {r.distance_km:.0f} 公里，跨区成本较高",
                            day_index=day.day_index, item_id=item.item_id,
                        )
                    )

        # 7. missing_route_data
        for day in plan.days:
            for i, item in enumerate(day.items):
                if i > 0 and item.route_from_previous is None:
                    checks.append(
                        ValidationCheck(
                            code="missing_route_data", severity="warning",
                            message=f"第{day.day_index}天 {item.poi.canonical_name} 缺少路段数据，交通待确认",
                            day_index=day.day_index, item_id=item.item_id,
                        )
                    )

        # 8. stale_claim（把历史内容描述为实时/当前营业/实时票价）
        stale_kw = ["实时", "当前票价", "现在营业", "今日客流", "实时客流"]
        text = plan.overview + "".join(
            item.booking_reminder or "" for day in plan.days for item in day.items
        )
        for kw in stale_kw:
            if kw in text:
                checks.append(
                    ValidationCheck(
                        code="stale_claim", severity="warning",
                        message=f"存在疑似实时断言「{kw}」，需用户确认",
                    )
                )

        # 9-13. 出片点级校验
        for day in plan.days:
            for item in day.items:
                hit = photo_hits.get(item.poi.poi_id)
                valid_spot_ids = {s.spot_id for s in hit.hits} if hit else set()
                for spot in item.photo_spots:
                    if spot.poi_id != item.poi.poi_id or spot.spot_id not in valid_spot_ids:
                        checks.append(
                            ValidationCheck(
                                code="invalid_photo_spot", severity="spot_fail",
                                message=f"出片点 {spot.spot_name} 不在对应景点检索结果中",
                                day_index=day.day_index, item_id=item.item_id, spot_id=spot.spot_id,
                            )
                        )
                    if not spot.coordinate:
                        checks.append(
                            ValidationCheck(
                                code="missing_spot_coordinate", severity="spot_fail",
                                message=f"出片点 {spot.spot_name} 缺少坐标",
                                day_index=day.day_index, item_id=item.item_id, spot_id=spot.spot_id,
                            )
                        )
                    if not spot.location_description:
                        checks.append(
                            ValidationCheck(
                                code="missing_location_description", severity="spot_fail",
                                message=f"出片点 {spot.spot_name} 缺少位置说明",
                                day_index=day.day_index, item_id=item.item_id, spot_id=spot.spot_id,
                            )
                        )
                    for photo in spot.reference_photos:
                        if not (photo.source_id and photo.storage_url):
                            checks.append(
                                ValidationCheck(
                                    code="missing_photo_source", severity="spot_fail",
                                    message=f"出片点 {spot.spot_name} 照片缺少来源",
                                    day_index=day.day_index, item_id=item.item_id, spot_id=spot.spot_id,
                                )
                            )
                    if spot.best_time is not None and not spot.best_time.source_ids:
                        checks.append(
                            ValidationCheck(
                                code="unsupported_best_time", severity="spot_fail",
                                message=f"出片点 {spot.spot_name} 最佳时间缺少来源证据",
                                day_index=day.day_index, item_id=item.item_id, spot_id=spot.spot_id,
                            )
                        )

        # 14. missing_lodging_recommendation
        if not plan.lodging_recommendations:
            checks.append(
                ValidationCheck(
                    code="missing_lodging_recommendation", severity="fail",
                    message="未输出住宿区域推荐",
                )
            )

        return checks

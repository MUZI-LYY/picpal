"""出片点结构化库：加载 + 自动准入校验 + 检索（结构化过滤 + 关键词 + 重排）。

本阶段用 JSON 文件 + 内存索引；向量检索待 Embedding 模型选型后接入，
语料规模增长后再评估 Chroma。
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Optional

from ..schemas.photo_spot import (
    PhotoSpotHit,
    ReferencePhoto,
    BestTime,
    SourceRef,
    Coordinate,
)

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "seed_photo_spots.json"
LOCAL_PHOTO_DIR = Path(__file__).resolve().parents[1] / "static" / "photos"

# 自动准入规则允许的位置精度（PRD 第九节：首版只接受 exact_poi 或 named_sub_poi）
_ALLOWED_PRECISION = {"exact_poi", "named_sub_poi"}


def local_photo_url(image_id: str) -> str | None:
    """若采集图片已落盘，返回同源静态地址，避免依赖第三方 CDN。"""
    match = re.fullmatch(r"image:([0-9a-f]+):(\d+)", image_id)
    if match is None:
        return None
    filename = f"{match.group(1)}-{match.group(2)}.webp"
    if not (LOCAL_PHOTO_DIR / filename).is_file():
        return None
    return f"/api/v1/photo-assets/{filename}"


class PhotoSpotStore:
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or DEFAULT_DATA_PATH
        self.records: dict[str, list[PhotoSpotHit]] = {}
        self._styles: dict[str, list[str]] = {}  # spot_id -> 扩展标签（用于关键词打分）
        self._poi_names: dict[str, str] = {}
        self._featured_ranks: dict[str, int] = {}
        self._load_file(self.data_path)

    # ---------- 加载与准入 ----------
    def _load_file(self, data_path: Path) -> None:
        if not data_path.exists():
            return
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        review_status_default = raw.get("_meta", {}).get("review_status_default")
        for rec in raw.get("photo_spots", []):
            # 仅用于一次性迁移试点期已经人工核对的 24 条历史数据；新文件若没有
            # 显式 approved，不会因代码默认值而进入正式检索库。
            if "review_status" not in rec and review_status_default == "approved":
                rec = {**rec, "review_status": "approved"}
            if not self._admit(rec):
                continue
            hit = self._to_hit(rec)
            self.records.setdefault(hit.poi_id, []).append(hit)
            if rec.get("poi_name"):
                self._poi_names[hit.poi_id] = str(rec["poi_name"])
            featured_rank = rec.get("featured_rank")
            if isinstance(featured_rank, int) and not isinstance(featured_rank, bool):
                self._featured_ranks[hit.spot_id] = featured_rank
            styles = (rec.get("photo_subjects") or []) + (rec.get("visual_styles") or [])
            self._styles[hit.spot_id] = [str(s) for s in styles]

    @staticmethod
    def _admit(rec: dict) -> bool:
        """自动准入规则（PRD 第九节）：只有通过校验的高置信记录才可在线推荐。"""
        if rec.get("ingestion_status") != "auto_verified":
            return False
        if rec.get("review_status") != "approved":
            return False
        if rec.get("publication_rights_status") not in {None, "approved"}:
            return False
        if not rec.get("spot_id") or not rec.get("poi_id"):
            return False
        if not rec.get("coordinate"):
            return False
        if not rec.get("location_description"):
            return False
        if rec.get("location_precision") not in _ALLOWED_PRECISION:
            return False
        if not rec.get("admission_evidence"):
            return False
        return True

    def poi_name(self, poi_id: str) -> str | None:
        return self._poi_names.get(poi_id)

    @staticmethod
    def _to_hit(rec: dict) -> PhotoSpotHit:
        return PhotoSpotHit(
            spot_id=rec["spot_id"],
            poi_id=rec["poi_id"],
            spot_name=rec["spot_name"],
            coordinate=Coordinate(**rec["coordinate"]),
            location_description=rec["location_description"],
            location_precision=rec["location_precision"],
            reference_photos=PhotoSpotStore._reference_photos(rec.get("reference_photos", [])),
            best_time=BestTime(**rec["best_time"]) if rec.get("best_time") else None,
            source_refs=[SourceRef(**s) for s in rec.get("source_refs", [])],
            ingestion_status=rec.get("ingestion_status", "auto_verified"),
            confidence=float(rec.get("confidence", 0.5)),
        )

    @staticmethod
    def _reference_photo(rec: dict) -> ReferencePhoto | None:
        """只暴露仓库内明确提供的图片，绝不回退到第三方外链。"""
        local_url = local_photo_url(str(rec.get("image_id", "")))
        if local_url is None:
            return None
        return ReferencePhoto(
            **{
                **rec,
                "storage_url": local_url,
                "thumbnail_url": local_url,
            }
        )

    @staticmethod
    def _reference_photos(records: list[dict]) -> list[ReferencePhoto]:
        return [
            photo
            for item in records
            if (photo := PhotoSpotStore._reference_photo(item)) is not None
        ]

    # ---------- 检索 ----------
    def search(self, poi_id: str, preferences: list[str], limit: int = 3) -> list[PhotoSpotHit]:
        """结构化过滤（poi_id + 准入已在上游）→ 关键词打分 → 重排 → top-N。"""
        candidates = self.records.get(poi_id, [])
        if not candidates:
            return []
        scored = sorted(
            ((self._score(hit, preferences), hit) for hit in candidates),
            key=lambda x: -x[0],
        )
        return [hit for _, hit in scored[:limit]]

    def featured(self, limit: int = 5) -> list[PhotoSpotHit]:
        """返回首页精选机位，优先覆盖不同景点，再按置信度补足。"""
        if limit <= 0:
            return []
        curated = sorted(
            (
                hit
                for spots in self.records.values()
                for hit in spots
                if hit.spot_id in self._featured_ranks
            ),
            key=lambda hit: (self._featured_ranks[hit.spot_id], hit.spot_id),
        )
        ranked_groups = [
            sorted(
                spots,
                key=lambda hit: (
                    not hit.reference_photos,
                    -hit.confidence,
                    hit.spot_id,
                ),
            )
            for _, spots in sorted(self.records.items())
            if spots
        ]
        selected = curated[:limit]
        selected_ids = {hit.spot_id for hit in selected}
        selected_pois = {hit.poi_id for hit in selected}
        for group in ranked_groups:
            if len(selected) >= limit:
                break
            if group[0].poi_id in selected_pois:
                continue
            selected.append(group[0])
            selected_ids.add(group[0].spot_id)
            selected_pois.add(group[0].poi_id)
        remaining = sorted(
            (hit for group in ranked_groups for hit in group if hit.spot_id not in selected_ids),
            key=lambda hit: (
                not hit.reference_photos,
                -hit.confidence,
                hit.spot_id,
            ),
        )
        return (selected + remaining)[:limit]

    def _score(self, hit: PhotoSpotHit, preferences: list[str]) -> float:
        score = float(hit.confidence)
        if not preferences:
            return score
        haystack = " ".join(self._styles.get(hit.spot_id, []) + [hit.spot_name, hit.location_description])
        matched = sum(1 for p in preferences if p and p in haystack)
        score += min(matched, 3) * 0.1
        return round(score, 3)

    def count(self) -> int:
        return sum(len(v) for v in self.records.values())

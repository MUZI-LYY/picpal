"""任务与行程持久化：带 schema 版本的 JSON 文件 + 原子写入。

本阶段为单用户、无并发场景，采用结构化文件持久化；
出现多用户/复杂查询/并发修改时迁移 SQLite + SQLAlchemy。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import TRIPS_DIR
from .errors import AppError

STORE_SCHEMA_VERSION = "1.0.0"

# 状态机（对齐 PRD 六）
STAGES = [
    "parsing",
    "planning",
    "retrieving_photo_spots",
    "draft",
    "validating",
    "validated",
]
FAILURE_STATES = {
    "parse_failed",
    "map_failed",
    "planning_failed",
    "validation_failed",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return f"task:{datetime.now().strftime('%Y%m%d')}:{uuid.uuid4().hex[:12]}"


class TripStore:
    """行程任务的 JSON 文件存储。"""

    def __init__(self, base_dir: Path = TRIPS_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        # 任务 ID 本身受控（服务端生成），防御性过滤路径分隔符
        safe = task_id.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe}.json"

    def create(self, task_id: str, input_text: str, input_fields: dict[str, Any]) -> dict[str, Any]:
        record = {
            "schema_version": STORE_SCHEMA_VERSION,
            "task_id": task_id,
            "status": "parsing",
            "stage_history": [{"stage": "parsing", "at": now_iso()}],
            "input_text": input_text,
            "input_fields": input_fields,
            "parsed_request": None,
            "plan": None,
            "error": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self._atomic_write(task_id, record)
        return record

    def get(self, task_id: str) -> Optional[dict[str, Any]]:
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise AppError("store_corrupted", f"任务记录损坏: {task_id}") from exc

    def update(self, task_id: str, **fields: Any) -> dict[str, Any]:
        record = self.get(task_id)
        if record is None:
            raise AppError("not_found", f"任务不存在: {task_id}", http_status=404)
        record.update(fields)
        record["updated_at"] = now_iso()
        self._atomic_write(task_id, record)
        return record

    def set_stage(self, task_id: str, stage: str) -> dict[str, Any]:
        record = self.get(task_id)
        if record is None:
            raise AppError("not_found", f"任务不存在: {task_id}", http_status=404)
        record["status"] = stage
        record["stage_history"] = list(record.get("stage_history", [])) + [
            {"stage": stage, "at": now_iso()}
        ]
        record["updated_at"] = now_iso()
        self._atomic_write(task_id, record)
        return record

    def _atomic_write(self, task_id: str, record: dict[str, Any]) -> None:
        path = self._path(task_id)
        fd, tmp = tempfile.mkstemp(dir=str(self.base_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


store = TripStore()

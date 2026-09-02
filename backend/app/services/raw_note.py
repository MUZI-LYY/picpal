"""原始采集笔记：数据模型与 JSONL 存储（数据采集环节 1 的产出）。

采集脚本（ego-browser 驱动）抓取小红书/马蜂窝等平台的机位笔记，
以 JSONL 落盘（每行一条笔记）；本模块定义笔记 schema 与读写，
供准入管线（环节 2-6，AdmissionPipeline.process_note）消费。

供离线准入管线消费，运行时数据写入被 Git 忽略的 data/raw_notes/。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..core.config import DATA_DIR

RAW_NOTES_DIR = DATA_DIR / "raw_notes"

SCHEMA_VERSION = "1.0.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoTag(BaseModel):
    """笔记定位标签（如有）。lng/lat 为 GCJ-02（国内平台基本为火星坐标）。"""

    name: str = ""
    lng: Optional[float] = None
    lat: Optional[float] = None


class RawNote(BaseModel):
    """一条原始采集笔记 = 一个最小采集单元（整篇笔记，含多个机位时由准入管线拆分）。"""

    source_id: str  # 唯一，如 xh:{note_id}
    source_platform: str  # xiaohongshu / mafengwo / dianping ...
    note_id: str  # 平台内笔记 id
    title: str
    text: str  # 正文全文（LLM 提取证据用，原文完整保存）
    author: str = ""
    source_url: str = ""  # 原始链接（版权追溯）
    published_at: str = ""  # 原文发布时间（保留平台原文，不做解析）
    collected_at: str = Field(default_factory=now_iso)
    geo: Optional[GeoTag] = None
    images: list[str] = Field(default_factory=list)  # 图片 URL
    query: str = ""  # 采集用的搜索词（溯源）

    def to_pipeline_note(self) -> dict:
        """转成 AdmissionPipeline.process_note 期望的 note dict。"""
        note: dict = {
            "text": self.text,
            "source_url": self.source_url,
            "author": self.author,
            "images": self.images,
        }
        if self.geo is not None and self.geo.lng is not None and self.geo.lat is not None:
            note["geo"] = {
                "name": self.geo.name,
                "lng": self.geo.lng,
                "lat": self.geo.lat,
            }
        return note


class RawNoteStore:
    """JSONL 存储：data/raw_notes/{name}.jsonl，每行一条 RawNote。"""

    def __init__(self, base_dir: Path = RAW_NOTES_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe}.jsonl"

    def append(self, name: str, note: RawNote) -> None:
        """追加一条笔记（原子追加，避免并发损坏）。"""
        path = self.path_for(name)
        line = json.dumps(note.model_dump(), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def append_many(self, name: str, notes: list[RawNote]) -> None:
        for n in notes:
            self.append(name, n)

    def read_all(self, name: str) -> list[RawNote]:
        path = self.path_for(name)
        if not path.exists():
            return []
        out: list[RawNote] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(RawNote.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return out

    def iter_files(self) -> list[Path]:
        return sorted(self.base_dir.glob("*.jsonl"))

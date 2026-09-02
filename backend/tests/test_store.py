"""持久化：原子写入、schema 版本、重启恢复。"""
from __future__ import annotations

import json

from app.core.store import TripStore, STORE_SCHEMA_VERSION


def test_create_and_get(tmp_path):
    s = TripStore(tmp_path)
    rec = s.create("task:1", "去北京", {"days": 3})
    assert rec["schema_version"] == STORE_SCHEMA_VERSION
    assert rec["status"] == "parsing"
    got = s.get("task:1")
    assert got["input_text"] == "去北京"


def test_update_and_stage(tmp_path):
    s = TripStore(tmp_path)
    s.create("task:1", "x", {})
    s.set_stage("task:1", "planning")
    s.update("task:1", plan={"title": "测试"})
    got = s.get("task:1")
    assert got["status"] == "planning"
    assert got["plan"]["title"] == "测试"
    assert len(got["stage_history"]) == 2  # parsing + planning


def test_recovery_across_instances(tmp_path):
    s1 = TripStore(tmp_path)
    s1.create("task:1", "x", {})
    s1.update("task:1", status="validated")
    # 模拟进程重启：新实例读同一目录
    s2 = TripStore(tmp_path)
    assert s2.get("task:1")["status"] == "validated"


def test_atomic_write_no_tmp_left(tmp_path):
    s = TripStore(tmp_path)
    s.create("task:1", "x", {})
    s.update("task:1", status="validated")
    leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_get_missing_returns_none(tmp_path):
    s = TripStore(tmp_path)
    assert s.get("task:nope") is None


def test_task_id_path_sanitized(tmp_path):
    s = TripStore(tmp_path)
    s.create("task:../evil", "x", {})
    # 不应产生越界文件
    assert not (tmp_path.parent / "evil.json").exists()

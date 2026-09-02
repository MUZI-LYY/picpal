"""时间工具：HH:MM 加减分钟、比较。"""
from __future__ import annotations


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def from_minutes(total: int) -> str:
    total = max(0, min(total, 24 * 60 - 1))
    return f"{total // 60:02d}:{total % 60:02d}"


def add_minutes(hhmm: str, minutes: int) -> str:
    return from_minutes(to_minutes(hhmm) + minutes)

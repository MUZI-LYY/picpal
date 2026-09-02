"""Alembic 初始迁移的升级和回滚测试。"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_initial_migration_up_and_down(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = _config(database_url)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    expected = {
        "anonymous_sessions",
        "conversations",
        "messages",
        "runs",
        "run_stage_events",
        "plan_versions",
        "retrieval_runs",
    }
    assert expected <= set(inspector.get_table_names())
    assert "uq_runs_active_per_conversation" in {
        index["name"] for index in inspector.get_indexes("runs")
    }
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(database_url)
    assert not (expected & set(inspect(engine).get_table_names()))
    engine.dispose()

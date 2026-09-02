"""SQLite Engine 与 Session 工厂。"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

from ..core.config import DATA_DIR, settings


def _default_database_url() -> str:
    """数据库连接串：优先取 DATABASE_URL 环境变量，否则按 env 用默认路径。"""
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{DATA_DIR / 'app.db'}"


def create_sqlite_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    if database_url is None:
        database_url = _default_database_url()
    if not database_url.startswith("sqlite:"):
        raise ValueError("本阶段只支持 SQLite DATABASE_URL")
    engine = create_engine(
        database_url,
        echo=echo,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_sqlite_engine()


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)

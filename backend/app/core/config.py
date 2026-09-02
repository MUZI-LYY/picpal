"""配置读取。密钥只从环境变量读取，代码不硬编码。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv  # type: ignore

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
PROJECT_ROOT = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "app" / "static"

load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    map_api_key: str = os.getenv("MAP_API_KEY", "")
    map_provider: str = os.getenv("MAP_PROVIDER", "")
    # 视觉审核模型（豆包，用于出片点图片质量审核）
    vision_api_key: str = os.getenv("VISION_API_KEY", "")
    vision_base_url: str = os.getenv("VISION_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    vision_model: str = os.getenv("VISION_MODEL", "doubao-seed-2-1-turbo-260628")
    session_signing_secret: str = os.getenv("SESSION_SIGNING_SECRET", "")
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    # 运行环境：dev / prod（prod 时数据库与文件目录切到 /tmp）
    env: str = os.getenv("ENV", "dev")
    # 数据库连接串；未设置时由 env 决定默认路径
    database_url: str = os.getenv("DATABASE_URL", "")
    # 内测邀请码：逗号分隔，如 "code1,code2,code3"
    invite_codes: str = os.getenv("INVITE_CODES", "")

    @property
    def is_prod(self) -> bool:
        return self.env.lower() == "prod"

    @property
    def has_real_llm(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def valid_invite_codes(self) -> set[str]:
        return {c.strip() for c in self.invite_codes.split(",") if c.strip()}

    @property
    def has_vision(self) -> bool:
        return bool(self.vision_api_key)


settings = Settings()

# 数据目录：生产环境（veFaaS）除 /tmp 外只读，数据库/文件写到 /tmp/data。
if settings.is_prod:
    DATA_DIR = Path("/tmp/data")
else:
    DATA_DIR = PROJECT_ROOT / "data"
TRIPS_DIR = DATA_DIR / "trips"

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRIPS_DIR.mkdir(parents=True, exist_ok=True)

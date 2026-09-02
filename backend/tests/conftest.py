"""测试全局配置：禁用真实 LLM，保证测试快速、确定性。"""
import pytest


@pytest.fixture(autouse=True)
def _disable_real_llm_intent(monkeypatch):
    # API 层注入的意图解析器在测试中返回 None，走纯规则。
    monkeypatch.setattr("app.api.conversations.get_intent_parser", lambda: None)


@pytest.fixture(autouse=True)
def _set_test_invite_codes(monkeypatch):
    # 测试环境统一使用固定邀请码 "test-invite"。
    from app.core.config import settings

    monkeypatch.setattr(settings, "invite_codes", "test-invite")

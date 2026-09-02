"""LLM 客户端：调用 DeepSeek（OpenAI 兼容）接口。

密钥只从后端配置读取，错误信息不泄露密钥与请求体。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from ..core.config import settings
from ..core.errors import AppError


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 90.0,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout

    def complete_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """返回解析后的 JSON 对象；失败抛 AppError（不泄露密钥）。"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise AppError("llm_timeout", "模型调用超时") from exc
        except httpx.HTTPError as exc:
            raise AppError("llm_network_error", "模型网络请求失败") from exc

        if resp.status_code != 200:
            raise AppError("llm_api_error", f"模型服务返回错误(HTTP {resp.status_code})")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AppError("llm_bad_response", "模型响应结构异常") from exc

        return self._parse_json(content)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        # 去掉可能的 markdown 代码块围栏
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        # 兜底：提取第一个平衡的 {...}
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[start : i + 1])
                            if isinstance(obj, dict):
                                return obj
                        except json.JSONDecodeError:
                            break
        raise AppError("llm_bad_json", "模型输出无法解析为 JSON")

"""视觉审核客户端：调用豆包多模态模型，判断图片是否适合出片点参考图。

用于过滤采集笔记里混入的地图/截图/拼接图/纯文字图，只保留风景/建筑/人物照。
接口为 OpenAI 兼容（火山方舟），图片用 image_url 传入。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from ..core.config import settings
from ..core.errors import AppError

# 审核提示词：判断图片是否适合作为出片点参考图
_SYSTEM = "你是出片点参考图质量审核助手，只输出 JSON。"

_USER_TEXT = (
    "判断这张图片是否适合作为「景点出片点参考图」（展示拍摄机位/效果的实拍照片）。\n"
    "适合(suitable=true)：风景照、建筑照、人物打卡照、自然景观照。\n"
    "不适合(suitable=false)：地图、路线图、手机屏幕截图、上下拼接的长图、纯文字图、海报、商品图、表情包、证件照、二维码。\n"
    '只输出 JSON：{"suitable": true或false, "category": "照片分类", "reason": "简短理由"}'
)


class VisionClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or settings.vision_api_key
        self.base_url = (base_url or settings.vision_base_url).rstrip("/")
        self.model = model or settings.vision_model
        self.timeout = timeout
        self._cache: dict[str, dict[str, Any]] = {}  # image_url -> 审核结果

    def judge_photo(self, image_url: str) -> dict[str, Any]:
        """判断一张图是否适合出片点参考图，返回 {suitable, category, reason}。"""
        if image_url in self._cache:
            return self._cache[image_url]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": _USER_TEXT},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 500,
            # 关闭深度思考（图片审核是简单任务，避免 reasoning 浪费成本与延迟）
            "thinking": {"type": "disabled"},
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise AppError("vision_timeout", "视觉模型调用超时") from exc
        except httpx.HTTPError as exc:
            raise AppError("vision_network_error", "视觉模型网络请求失败") from exc

        if resp.status_code == 429:
            # 限流：退避重试
            for backoff in (1.0, 2.0, 4.0):
                import time as _time
                _time.sleep(backoff)
                try:
                    resp = httpx.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        timeout=self.timeout,
                    )
                except httpx.HTTPError:
                    continue
                if resp.status_code == 200:
                    break
        if resp.status_code != 200:
            raise AppError("vision_api_error", f"视觉模型返回错误(HTTP {resp.status_code})")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AppError("vision_bad_response", "视觉模型响应结构异常") from exc

        result = self._parse_json(content)
        self._cache[image_url] = result
        return result

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = (content or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
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
        raise AppError("vision_bad_json", "视觉模型输出无法解析为 JSON")

    def _judge_safe(self, image_url: str) -> Optional[dict[str, Any]]:
        """审核单张图，失败返回 None（不阻塞整批）。"""
        try:
            return self.judge_photo(image_url)
        except AppError:
            return None

    def filter_images(
        self,
        image_urls: list[str],
        limit: int = 0,
        concurrency: int = 4,
        on_progress=None,
    ) -> list[str]:
        """批量审核，返回适合作为参考图的图片 URL 列表（保持原顺序）。

        并行审核；审核失败/超时的图默认保留（不因审核失败而误删）。
        on_progress(done, total) 回调用于进度提示。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 去重（同一 URL 只审一次）
        unique: list[str] = []
        seen: set[str] = set()
        for u in image_urls:
            if u and u not in seen:
                seen.add(u)
                unique.append(u)

        # 默认保留（审核失败的图不误删）；只有明确 unsuitable 的才过滤
        ok: dict[str, bool] = {u: True for u in unique}
        done = 0
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = {ex.submit(self._judge_safe, u): u for u in unique}
            for f in as_completed(futures):
                u = futures[f]
                r = f.result()
                if r is not None:
                    ok[u] = r.get("suitable") is True
                done += 1
                if on_progress:
                    on_progress(done, len(unique))

        out: list[str] = []
        for u in image_urls:
            if ok.get(u) is True:
                out.append(u)
                if limit and len(out) >= limit:
                    break
        return out

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings


class OpenAICompatibleClient:
    """Tiny async client that works with OpenAI and compatible endpoints."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key) and not self.settings.demo_mode

    async def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        if not self.enabled:
            raise RuntimeError("LLM 未配置，当前应使用演示模式")
        url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        payload = {
            "model": self.settings.openai_model,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        raw = await self.complete(system, user, temperature=0.1)
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("模型没有返回 JSON 对象")
        return json.loads(match.group(0))

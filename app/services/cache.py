from __future__ import annotations

import json
from typing import Any


class TaskCache:
    """Redis task cache with an in-process fallback for local development."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._memory: dict[str, dict[str, Any]] = {}
        self._redis = None

    async def connect(self) -> None:
        try:
            from redis.asyncio import from_url

            client = from_url(self.redis_url, decode_responses=True, socket_connect_timeout=0.35)
            await client.ping()
            self._redis = client
        except Exception:
            self._redis = None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    async def set(self, key: str, value: dict[str, Any], ttl: int = 86_400) -> None:
        self._memory[key] = value
        if self._redis is not None:
            await self._redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))

    async def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is not None:
            raw = await self._redis.get(key)
            if raw:
                return json.loads(raw)
        return self._memory.get(key)

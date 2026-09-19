from __future__ import annotations

import asyncio
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.models import SourceDocument
from app.services.documents import load_documents
from app.services.retrieval import tokenize


class TavilySearchProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.tavily_api_key) and not self.settings.demo_mode

    async def search(self, query: str, limit: int) -> list[SourceDocument]:
        if not self.enabled:
            return []
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": limit,
            "include_raw_content": True,
        }
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
        documents: list[SourceDocument] = []
        for item in response.json().get("results", []):
            content = item.get("raw_content") or item.get("content") or ""
            url = item.get("url")
            if not content:
                continue
            documents.append(SourceDocument(
                title=item.get("title") or url or "未命名网页",
                url=url,
                domain=urlsplit(url).hostname or "" if url else "",
                content=content,
                snippet=re.sub(r"\s+", " ", item.get("content") or content)[:280],
                source_type="web",
                metadata={"provider": "tavily", "provider_score": item.get("score", 0)},
            ))
        return documents


class DemoSearchProvider:
    """Searches packaged evidence so the entire system is demonstrable offline."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._documents: list[SourceDocument] | None = None

    def _load(self) -> list[SourceDocument]:
        if self._documents is None:
            self._documents = load_documents(sorted(self.data_dir.glob("*")))
            for index, item in enumerate(self._documents, start=1):
                item.url = f"https://demo.local/source/{index}"
                item.domain = "demo.local"
                item.metadata["provider"] = "demo"
        return [item.model_copy(deep=True) for item in self._documents]

    async def search(self, query: str, limit: int) -> list[SourceDocument]:
        query_terms = set(tokenize(query))
        scored: list[tuple[float, SourceDocument]] = []
        for item in self._load():
            terms = set(tokenize(f"{item.title} {item.content}"))
            score = len(query_terms & terms) / max(len(query_terms), 1)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]


class MultiSourceSearchService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.web = TavilySearchProvider(settings)
        self.demo = DemoSearchProvider(settings.demo_data_dir)

    async def search_many(self, questions: list[str]) -> list[SourceDocument]:
        semaphore = asyncio.Semaphore(self.settings.max_concurrency)

        async def run(question: str) -> list[SourceDocument]:
            async with semaphore:
                provider = self.web if self.web.enabled else self.demo
                last_error: Exception | None = None
                for attempt in range(2):
                    try:
                        return await provider.search(question, self.settings.max_sources_per_query)
                    except (httpx.HTTPError, TimeoutError) as exc:
                        last_error = exc
                        await asyncio.sleep(0.25 * (attempt + 1))
                if self.web.enabled:
                    # Graceful degradation keeps a failed external dependency from killing the task.
                    return await self.demo.search(question, self.settings.max_sources_per_query)
                if last_error:
                    raise last_error
                return []

        batches = await asyncio.gather(*(run(question) for question in questions))
        return [document for batch in batches for document in batch]

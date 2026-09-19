from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path

from app.models import SourceDocument

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


class HashEmbedding:
    """Deterministic offline embedding used in demo/test mode."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            sign = 1.0 if (value >> 8) % 2 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(item * item for item in vector)) or 1.0
        return [item / norm for item in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


class ChromaVectorIndex:
    """Chroma-backed index with an in-memory fallback for zero-config demos."""

    def __init__(self, persist_dir: Path, collection_name: str = "research_sources") -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding = HashEmbedding()
        self._items: list[tuple[SourceDocument, list[float]]] = []
        self._collection = None
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(persist_dir))
            self._collection = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
        except Exception:
            self._collection = None

    def add(self, documents: list[SourceDocument]) -> None:
        if not documents:
            return
        embeddings = [self.embedding.embed(item.content) for item in documents]
        self._items.extend(zip(documents, embeddings, strict=False))
        if self._collection is not None:
            ids = [f"{item.source_id or 'doc'}-{item.fingerprint[:12]}-{index}" for index, item in enumerate(documents)]
            self._collection.upsert(
                ids=ids,
                documents=[item.content for item in documents],
                embeddings=embeddings,
                metadatas=[{"source_id": item.source_id, "title": item.title} for item in documents],
            )

    def scores(self, query: str, documents: list[SourceDocument]) -> dict[int, float]:
        query_vector = self.embedding.embed(query)
        return {id(item): max(0.0, cosine_similarity(query_vector, self.embedding.embed(item.content))) for item in documents}


class HybridReranker:
    """Combines vector, keyword and source-quality signals into a final rank."""

    def __init__(self, index: ChromaVectorIndex) -> None:
        self.index = index

    def rank(self, query: str, documents: list[SourceDocument], limit: int = 12) -> list[SourceDocument]:
        if not documents:
            return []
        query_terms = Counter(tokenize(query))
        vector_scores = self.index.scores(query, documents)
        for item in documents:
            terms = Counter(tokenize(f"{item.title} {item.content}"))
            overlap = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
            keyword = overlap / max(sum(query_terms.values()), 1)
            vector = vector_scores[id(item)]
            cross = min(item.cross_validation_count / 3.0, 1.0)
            item.keyword_score = round(min(keyword, 1.0), 4)
            item.vector_score = round(vector, 4)
            item.relevance_score = round(
                0.45 * vector + 0.30 * min(keyword, 1.0) + 0.18 * item.credibility_score + 0.07 * cross,
                4,
            )
        return sorted(documents, key=lambda item: item.relevance_score, reverse=True)[:limit]

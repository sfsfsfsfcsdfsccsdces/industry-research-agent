from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchMode(StrEnum):
    HYBRID = "hybrid"
    WEB = "web"
    LOCAL = "local"


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    mode: ResearchMode = ResearchMode.HYBRID
    max_questions: int | None = Field(default=None, ge=2, le=10)
    language: str = "zh-CN"


class ResearchTask(BaseModel):
    id: str
    query: str
    mode: ResearchMode
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    current_step: str = "等待执行"
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SourceDocument(BaseModel):
    source_id: str = ""
    title: str
    url: str | None = None
    content: str
    snippet: str = ""
    source_type: str = "web"
    domain: str = ""
    published_at: str | None = None
    fingerprint: str = ""
    credibility_score: float = 0.5
    relevance_score: float = 0.0
    keyword_score: float = 0.0
    vector_score: float = 0.0
    cross_validation_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    question: str
    claim: str
    source_ids: list[str]
    confidence: float = 0.5


class TraceEvent(BaseModel):
    task_id: str
    event: str
    message: str
    progress: int
    node: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ReportResult(BaseModel):
    task_id: str
    title: str
    markdown: str
    source_count: int
    citation_count: int
    generated_at: datetime = Field(default_factory=utc_now)
    files: dict[str, str] = Field(default_factory=dict)

from __future__ import annotations

from typing import Any, TypedDict

from app.models import ResearchMode, SourceDocument


class ResearchState(TypedDict, total=False):
    task_id: str
    query: str
    mode: ResearchMode
    max_questions: int
    questions: list[str]
    sources: list[SourceDocument]
    ranked_sources: list[SourceDocument]
    context: str
    report: str
    files: dict[str, str]
    loop_count: int
    should_retry: bool
    warnings: list[str]
    metrics: dict[str, Any]

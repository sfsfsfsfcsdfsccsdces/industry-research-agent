from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from app.core.config import Settings
from app.models import ResearchMode, SourceDocument
from app.services.documents import load_and_chunk_documents
from app.services.exporter import ReportExporter
from app.services.llm import OpenAICompatibleClient
from app.services.planner import ResearchPlanner
from app.services.reporting import ReportWriter, compress_context, validate_citations
from app.services.retrieval import ChromaVectorIndex, HybridReranker
from app.services.search import MultiSourceSearchService
from app.services.source_quality import prepare_and_deduplicate
from app.workflow.state import ResearchState

EventSink = Callable[[str, str, int, dict], Awaitable[None]]


async def _noop_sink(node: str, message: str, progress: int, payload: dict) -> None:
    return None


class ResearchWorkflow:
    """Plan-search-rank-write LangGraph with bounded quality-retry loops."""

    def __init__(self, settings: Settings, event_sink: EventSink | None = None) -> None:
        self.settings = settings
        self.event_sink = event_sink or _noop_sink
        self.llm = OpenAICompatibleClient(settings)
        self.planner = ResearchPlanner(self.llm)
        self.search = MultiSourceSearchService(settings)
        self.vector_index = ChromaVectorIndex(settings.chroma_path)
        self.reranker = HybridReranker(self.vector_index)
        self.writer = ReportWriter(self.llm)
        self.exporter = ReportExporter(settings.report_dir)
        self.graph = self._build_graph()

    async def _emit(self, node: str, message: str, progress: int, **payload) -> None:
        await self.event_sink(node, message, progress, payload)

    def _build_graph(self):
        builder = StateGraph(ResearchState)
        builder.add_node("planner", self._plan)
        builder.add_node("retriever", self._retrieve)
        builder.add_node("quality_gate", self._quality_gate)
        builder.add_node("compressor", self._compress)
        builder.add_node("writer", self._write)
        builder.add_node("validator", self._validate)
        builder.add_node("exporter", self._export)
        builder.add_edge(START, "planner")
        builder.add_edge("planner", "retriever")
        builder.add_edge("retriever", "quality_gate")
        builder.add_conditional_edges(
            "quality_gate",
            lambda state: "retry" if state.get("should_retry") else "continue",
            {"retry": "retriever", "continue": "compressor"},
        )
        builder.add_edge("compressor", "writer")
        builder.add_edge("writer", "validator")
        builder.add_edge("validator", "exporter")
        builder.add_edge("exporter", END)
        return builder.compile()

    async def _plan(self, state: ResearchState) -> dict:
        await self._emit("planner", "正在拆解研究目标并生成子问题", 10)
        questions = await self.planner.plan(state["query"], state["max_questions"])
        await self._emit("planner", f"已生成 {len(questions)} 个去重研究问题", 18, questions=questions)
        return {"questions": questions, "loop_count": 0, "sources": [], "warnings": []}

    def _uploaded_documents(self) -> list[SourceDocument]:
        paths = [path for path in self.settings.upload_dir.glob("*") if path.is_file()]
        return load_and_chunk_documents(paths)

    async def _retrieve(self, state: ResearchState) -> dict:
        loop_count = state.get("loop_count", 0)
        await self._emit("retriever", "正在并行检索网页与本地资料", 28 + loop_count * 7)
        mode = state["mode"]
        found: list[SourceDocument] = list(state.get("sources", []))
        if mode in (ResearchMode.WEB, ResearchMode.HYBRID):
            found.extend(await self.search.search_many(state["questions"]))
        if mode in (ResearchMode.LOCAL, ResearchMode.HYBRID):
            local = self._uploaded_documents()
            if not local and self.settings.demo_mode:
                local = load_and_chunk_documents(sorted(self.settings.demo_data_dir.glob("*")))
            found.extend(local)
        await self._emit("retriever", f"检索得到 {len(found)} 条原始资料", 39 + loop_count * 7)
        return {"sources": found}

    async def _quality_gate(self, state: ResearchState) -> dict:
        await self._emit("quality_gate", "正在执行 URL/内容去重、可信度评分与跨来源支持度分析", 49)
        prepared = prepare_and_deduplicate(state.get("sources", []))
        self.vector_index.add(prepared)
        ranked = self.reranker.rank(state["query"] + " " + " ".join(state["questions"]), prepared, limit=14)
        accepted = [item for item in ranked if item.relevance_score >= self.settings.relevance_threshold]
        if len(accepted) < min(4, len(ranked)):
            accepted = ranked[: min(8, len(ranked))]
        loop_count = state.get("loop_count", 0) + 1
        should_retry = len(accepted) < 3 and loop_count < self.settings.max_research_loops
        questions = state["questions"]
        if should_retry:
            questions = questions + [f"{state['query']} 官方文档、用户案例与已知限制有哪些？"]
        await self._emit(
            "quality_gate",
            f"保留 {len(accepted)} 个高相关来源" + ("，证据不足，准备补充检索" if should_retry else ""),
            58,
            accepted=len(accepted), retry=should_retry,
        )
        return {
            "ranked_sources": accepted,
            "sources": prepared,
            "loop_count": loop_count,
            "should_retry": should_retry,
            "questions": questions,
            "metrics": {
                "raw_sources": len(state.get("sources", [])),
                "deduplicated_sources": len(prepared),
                "accepted_sources": len(accepted),
            },
        }

    async def _compress(self, state: ResearchState) -> dict:
        await self._emit("compressor", "正在抽取证据片段、控制上下文预算并保留引用锚点", 68)
        context = compress_context(state.get("ranked_sources", []), self.settings.context_char_limit)
        return {"context": context}

    async def _write(self, state: ResearchState) -> dict:
        await self._emit("writer", "Writer Agent 正在生成结构化调研报告", 78)
        report = await self.writer.write(
            state["query"], state["questions"], state["context"], state.get("ranked_sources", [])
        )
        return {"report": report}

    async def _validate(self, state: ResearchState) -> dict:
        await self._emit("validator", "正在校验引用完整性与报告结构", 88)
        report, warnings = validate_citations(state["report"], state.get("ranked_sources", []))
        required = ("执行摘要", "研究范围", "竞品", "风险", "建议", "参考来源")
        missing = [heading for heading in required if heading not in report]
        if missing:
            warnings.append(f"报告缺少建议章节：{', '.join(missing)}")
        return {"report": report, "warnings": state.get("warnings", []) + warnings}

    async def _export(self, state: ResearchState) -> dict:
        await self._emit("exporter", "正在导出 Markdown、Word 和 PDF", 95)
        files = await asyncio.to_thread(self.exporter.export_all, state["task_id"], state["report"])
        await self._emit("exporter", "报告生成完成", 100, files=files)
        return {"files": files}

    async def run(self, task_id: str, query: str, mode: ResearchMode, max_questions: int) -> ResearchState:
        initial: ResearchState = {
            "task_id": task_id,
            "query": query,
            "mode": mode,
            "max_questions": max_questions,
        }
        return await self.graph.ainvoke(initial, {"recursion_limit": 30})

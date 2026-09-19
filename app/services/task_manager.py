from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.models import ReportResult, ResearchRequest, ResearchTask, TaskStatus, TraceEvent, utc_now
from app.services.cache import TaskCache
from app.services.store import SQLiteStore
from app.workflow.graph import ResearchWorkflow

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, settings: Settings, store: SQLiteStore, cache: TaskCache) -> None:
        self.settings = settings
        self.store = store
        self.cache = cache
        self.queues: dict[str, list[asyncio.Queue[dict]]] = defaultdict(list)
        self.running: set[asyncio.Task] = set()
        self.semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def create(self, request: ResearchRequest) -> ResearchTask:
        task = ResearchTask(id=uuid4().hex, query=request.query, mode=request.mode)
        self.store.save_task(task)
        await self.cache.set(f"task:{task.id}", task.model_dump(mode="json"))
        job = asyncio.create_task(self._run(task, request), name=f"research-{task.id}")
        self.running.add(job)
        job.add_done_callback(self.running.discard)
        return task

    async def _run(self, task: ResearchTask, request: ResearchRequest) -> None:
        async with self.semaphore:
            task.status = TaskStatus.RUNNING
            task.current_step = "启动 Agent 工作流"
            task.updated_at = utc_now()
            self.store.save_task(task)

            async def sink(node: str, message: str, progress: int, payload: dict) -> None:
                task.progress = progress
                task.current_step = message
                task.updated_at = utc_now()
                self.store.save_task(task)
                await self.cache.set(f"task:{task.id}", task.model_dump(mode="json"))
                event = TraceEvent(task_id=task.id, event="progress", message=message, progress=progress, node=node, payload=payload)
                self.store.add_trace(event)
                await self._publish(task.id, event.model_dump(mode="json"))

            try:
                workflow = ResearchWorkflow(self.settings, sink)
                state = await workflow.run(
                    task.id, request.query, request.mode,
                    request.max_questions or self.settings.max_sub_questions,
                )
                sources = state.get("ranked_sources", [])
                self.store.save_sources(task.id, sources)
                report = ReportResult(
                    task_id=task.id,
                    title=f"{request.query}：智能调研报告",
                    markdown=state["report"],
                    source_count=len(sources),
                    citation_count=state["report"].count("[S"),
                    files=state.get("files", {}),
                )
                self.store.save_report(report)
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.current_step = "报告生成完成"
                task.updated_at = utc_now()
                self.store.save_task(task)
                await self.cache.set(f"task:{task.id}", task.model_dump(mode="json"))
                await self._publish(task.id, {"event": "complete", "task_id": task.id, "progress": 100})
            except Exception as exc:
                logger.exception("Research task %s failed", task.id)
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                task.current_step = "执行失败"
                task.updated_at = utc_now()
                self.store.save_task(task)
                await self.cache.set(f"task:{task.id}", task.model_dump(mode="json"))
                await self._publish(task.id, {"event": "error", "task_id": task.id, "message": str(exc)})

    async def _publish(self, task_id: str, event: dict) -> None:
        for queue in list(self.queues[task_id]):
            await queue.put(event)

    async def subscribe(self, task_id: str):
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self.queues[task_id].append(queue)
        try:
            task = self.store.get_task(task_id)
            if task:
                yield {"event": "snapshot", "task": task.model_dump(mode="json")}
            while True:
                current = self.store.get_task(task_id)
                if current and current.status in {TaskStatus.COMPLETED, TaskStatus.FAILED} and queue.empty():
                    yield {
                        "event": "complete" if current.status == TaskStatus.COMPLETED else "error",
                        "task_id": task_id,
                        "message": current.error,
                    }
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield event
                    if event.get("event") in {"complete", "error"}:
                        break
                except TimeoutError:
                    yield {"event": "heartbeat", "task_id": task_id}
        finally:
            self.queues[task_id].remove(queue)

    def resolve_report_file(self, task_id: str, format_name: str) -> Path | None:
        report = self.store.get_report(task_id)
        if not report or format_name not in report.files:
            return None
        path = Path(report.files[format_name]).resolve()
        allowed = self.settings.report_dir.resolve()
        if allowed not in path.parents or not path.is_file():
            return None
        return path

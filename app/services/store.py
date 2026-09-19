from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from app.models import ReportResult, ResearchTask, SourceDocument, TaskStatus, TraceEvent, utc_now


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, query TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, progress INTEGER NOT NULL, current_step TEXT NOT NULL,
                    error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    task_id TEXT NOT NULL, source_id TEXT NOT NULL, title TEXT NOT NULL,
                    url TEXT, content TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (task_id, source_id)
                );
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    event TEXT NOT NULL, node TEXT NOT NULL, message TEXT NOT NULL,
                    progress INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    task_id TEXT PRIMARY KEY, title TEXT NOT NULL, markdown TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    def save_task(self, task: ResearchTask) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("""
                INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status, progress=excluded.progress,
                current_step=excluded.current_step, error=excluded.error, updated_at=excluded.updated_at
            """, (
                task.id, task.query, task.mode.value, task.status.value, task.progress,
                task.current_step, task.error, task.created_at.isoformat(), task.updated_at.isoformat(),
            ))

    def get_task(self, task_id: str) -> ResearchTask | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return ResearchTask(**dict(row))

    def list_tasks(self, limit: int = 20) -> list[ResearchTask]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [ResearchTask(**dict(row)) for row in rows]

    def save_sources(self, task_id: str, sources: list[SourceDocument]) -> None:
        with self._lock, self._connect() as connection:
            connection.executemany("""
                INSERT OR REPLACE INTO sources(task_id, source_id, title, url, content, payload)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [(task_id, item.source_id, item.title, item.url, item.content, item.model_dump_json()) for item in sources])

    def get_sources(self, task_id: str) -> list[SourceDocument]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM sources WHERE task_id=? ORDER BY source_id", (task_id,)).fetchall()
        return [SourceDocument.model_validate_json(row["payload"]) for row in rows]

    def add_trace(self, event: TraceEvent) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("""
                INSERT INTO traces(task_id,event,node,message,progress,payload,created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event.task_id, event.event, event.node, event.message, event.progress,
                    json.dumps(event.payload, ensure_ascii=False), event.created_at.isoformat()))

    def get_traces(self, task_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM traces WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
        return [dict(row) | {"payload": json.loads(row["payload"])} for row in rows]

    def save_report(self, report: ReportResult) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("""
                INSERT OR REPLACE INTO reports(task_id,title,markdown,payload,created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (report.task_id, report.title, report.markdown, report.model_dump_json(), report.generated_at.isoformat()))

    def get_report(self, task_id: str) -> ReportResult | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM reports WHERE task_id=?", (task_id,)).fetchone()
        return ReportResult.model_validate_json(row["payload"]) if row else None

    def mark_failed(self, task_id: str, error: str) -> None:
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = error
            task.current_step = "执行失败"
            task.updated_at = utc_now()
            self.save_task(task)

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.models import ResearchRequest
from app.services.documents import SUPPORTED_SUFFIXES

router = APIRouter(prefix="/api")


def _manager(request: Request):
    return request.app.state.task_manager


@router.post("/research", status_code=202)
async def create_research(payload: ResearchRequest, request: Request):
    task = await _manager(request).create(payload)
    return task


@router.get("/research")
async def list_research(request: Request, limit: int = 20):
    return _manager(request).store.list_tasks(min(max(limit, 1), 100))


@router.get("/research/{task_id}")
async def get_research(task_id: str, request: Request):
    task = _manager(request).store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    report = _manager(request).store.get_report(task_id)
    return {"task": task, "report": report}


@router.get("/research/{task_id}/sources")
async def get_sources(task_id: str, request: Request):
    if not _manager(request).store.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return _manager(request).store.get_sources(task_id)


@router.get("/research/{task_id}/traces")
async def get_traces(task_id: str, request: Request):
    if not _manager(request).store.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return _manager(request).store.get_traces(task_id)


@router.get("/research/{task_id}/events")
async def research_events(task_id: str, request: Request):
    if not _manager(request).store.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")

    async def stream():
        async for event in _manager(request).subscribe(task_id):
            if await request.is_disconnected():
                break
            event_name = event.get("event", "progress")
            yield f"event: {event_name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/research/{task_id}/download/{format_name}")
async def download_report(task_id: str, format_name: str, request: Request):
    aliases = {"md": "markdown", "markdown": "markdown", "docx": "docx", "pdf": "pdf"}
    resolved = aliases.get(format_name.lower())
    if not resolved:
        raise HTTPException(status_code=400, detail="仅支持 md、docx、pdf")
    path = _manager(request).resolve_report_file(task_id, resolved)
    if not path:
        raise HTTPException(status_code=404, detail="报告文件不存在")
    media = {"markdown": "text/markdown", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "pdf": "application/pdf"}
    return FileResponse(path, media_type=media[resolved], filename=f"research-report.{path.suffix.lstrip('.')}")


@router.post("/documents", status_code=201)
async def upload_document(request: Request, file: Annotated[UploadFile, File(...)]):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持该格式，可上传：{', '.join(sorted(SUPPORTED_SUFFIXES))}")
    safe_stem = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]", "_", Path(file.filename or "document").stem)[:80]
    target = request.app.state.settings.upload_dir / f"{safe_stem}{suffix}"
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 10 MB")
    target.write_bytes(data)
    return {"filename": target.name, "size": len(data), "message": "上传成功，将在下一次 local/hybrid 调研中使用"}


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    return {
        "status": "ok",
        "mode": "demo" if settings.demo_mode else "production",
        "llm_configured": bool(settings.openai_api_key),
        "tavily_configured": bool(settings.tavily_api_key),
    }

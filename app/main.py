from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import ROOT_DIR, Settings, get_settings
from app.services.cache import TaskCache
from app.services.store import SQLiteStore
from app.services.task_manager import TaskManager


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or get_settings()
    selected.ensure_directories()
    logging.basicConfig(level=getattr(logging, selected.log_level.upper(), logging.INFO))

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        cache = TaskCache(selected.redis_url)
        await cache.connect()
        store = SQLiteStore(selected.database_path)
        application.state.settings = selected
        application.state.task_manager = TaskManager(selected, store, cache)
        yield
        for task in list(application.state.task_manager.running):
            task.cancel()
        await cache.close()

    application = FastAPI(
        title=selected.app_name,
        version="1.0.0",
        description="基于 LangGraph 的行业与竞品多源智能调研平台",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(router)
    application.mount("/static", StaticFiles(directory=ROOT_DIR / "app" / "static"), name="static")

    @application.get("/", include_in_schema=False)
    async def index():
        return FileResponse(ROOT_DIR / "app" / "static" / "index.html")

    return application


app = create_app()

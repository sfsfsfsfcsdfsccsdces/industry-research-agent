from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Demo mode works without any external credentials."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "行业与竞品智能调研报告生成平台"
    app_env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    log_level: str = "INFO"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    tavily_api_key: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    database_path: Path = ROOT_DIR / "runtime" / "research.db"
    chroma_path: Path = ROOT_DIR / "runtime" / "chroma"
    upload_dir: Path = ROOT_DIR / "runtime" / "uploads"
    report_dir: Path = ROOT_DIR / "runtime" / "reports"
    demo_data_dir: Path = ROOT_DIR / "data" / "demo"

    max_sub_questions: int = Field(default=5, ge=2, le=10)
    max_research_loops: int = Field(default=2, ge=1, le=4)
    max_sources_per_query: int = Field(default=5, ge=1, le=10)
    max_concurrency: int = Field(default=4, ge=1, le=12)
    request_timeout_seconds: float = Field(default=25.0, ge=3.0, le=120.0)
    relevance_threshold: float = Field(default=0.18, ge=0.0, le=1.0)
    context_char_limit: int = Field(default=18_000, ge=2_000, le=100_000)

    def ensure_directories(self) -> None:
        for path in (self.database_path.parent, self.chroma_path, self.upload_dir, self.report_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

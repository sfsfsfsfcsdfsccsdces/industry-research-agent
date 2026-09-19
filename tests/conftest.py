from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import ROOT_DIR, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        demo_mode=True,
        database_path=tmp_path / "research.db",
        chroma_path=tmp_path / "chroma",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        demo_data_dir=ROOT_DIR / "data" / "demo",
        max_sub_questions=4,
        max_research_loops=1,
        relevance_threshold=0.0,
    )

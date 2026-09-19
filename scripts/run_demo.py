from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.models import ResearchMode  # noqa: E402
from app.workflow.graph import ResearchWorkflow  # noqa: E402


async def main() -> None:
    settings = get_settings()

    async def progress(node: str, message: str, percent: int, payload: dict) -> None:
        print(f"[{percent:>3}%] {node:<12} {message}")

    query = "对比 Dify、FastGPT 与 RAGFlow 的定位和能力，并给出企业知识库选型建议"
    workflow = ResearchWorkflow(settings, progress)
    result = await workflow.run(uuid4().hex, query, ResearchMode.HYBRID, 5)
    print("\n完成：")
    for format_name, path in result["files"].items():
        print(f"- {format_name}: {path}")


if __name__ == "__main__":
    asyncio.run(main())

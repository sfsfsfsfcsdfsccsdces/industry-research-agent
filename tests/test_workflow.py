from pathlib import Path

import pytest

from app.models import ResearchMode
from app.workflow.graph import ResearchWorkflow


@pytest.mark.asyncio
async def test_demo_workflow_generates_cited_reports(settings):
    events = []

    async def sink(node, message, progress, payload):
        events.append((node, progress))

    workflow = ResearchWorkflow(settings, sink)
    result = await workflow.run("test-task", "Dify FastGPT RAGFlow 企业知识库选型", ResearchMode.HYBRID, 4)
    assert "执行摘要" in result["report"]
    assert "[S1]" in result["report"]
    assert len(result["ranked_sources"]) >= 3
    assert {node for node, _ in events} >= {"planner", "retriever", "quality_gate", "writer", "exporter"}
    assert all(Path(path).exists() for path in result["files"].values())

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app


def test_api_research_lifecycle(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["mode"] == "demo"

        created = client.post(
            "/api/research",
            json={"query": "Dify FastGPT RAGFlow 企业知识库选型", "mode": "hybrid", "max_questions": 3},
        )
        assert created.status_code == 202
        task_id = created.json()["id"]

        deadline = time.monotonic() + 10
        payload = {}
        while time.monotonic() < deadline:
            response = client.get(f"/api/research/{task_id}")
            assert response.status_code == 200
            payload = response.json()
            if payload["task"]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert payload["task"]["status"] == "completed"
        assert payload["report"]["source_count"] >= 3
        assert client.get(f"/api/research/{task_id}/download/pdf").status_code == 200

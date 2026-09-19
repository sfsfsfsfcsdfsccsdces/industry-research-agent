from app.models import ResearchMode, ResearchTask
from app.services.store import SQLiteStore


def test_sqlite_task_round_trip(tmp_path):
    store = SQLiteStore(tmp_path / "test.db")
    task = ResearchTask(id="task-1", query="测试问题", mode=ResearchMode.HYBRID)
    store.save_task(task)
    loaded = store.get_task("task-1")
    assert loaded is not None
    assert loaded.query == "测试问题"
    assert loaded.mode == ResearchMode.HYBRID

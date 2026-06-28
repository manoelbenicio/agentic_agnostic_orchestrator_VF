from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tasks_api.models import TaskPriority, TaskStatus
from tasks_api.router import build_tasks_router


class FakeReconciler:
    def __init__(self) -> None:
        self.calls = 0

    def reconcile_all(self):
        self.calls += 1
        return {
            "file": {"reconciled": 1, "errors": []},
            "herdmaster": {"synced": 0, "errors": []},
            "timestamp": "2026-06-27T22:50:44+00:00",
        }


def _client(tasks_repo, reconciler: FakeReconciler | None = None) -> TestClient:
    state = SimpleNamespace(tasks_repo=tasks_repo, tasks_reconciler=reconciler or FakeReconciler(), message_bus=None)
    app = FastAPI()
    app.include_router(build_tasks_router(lambda: state, prefix="/tasks"))
    return TestClient(app)


def test_router_lists_filters_and_updates_tasks(tasks_repo) -> None:
    tasks_repo.upsert(
        task_id="T",
        title="Backend unit tests",
        priority=TaskPriority.P2,
        agent="codex",
        pane="w3:pA",
        status=TaskStatus.WORKING,
        eta_min=60,
        progress=0,
    )
    tasks_repo.upsert(
        task_id="U",
        title="Security audit",
        priority=TaskPriority.P1,
        agent="codex",
        pane="w3:p5",
        status=TaskStatus.DONE,
        eta_min=0,
        progress=100,
    )
    client = _client(tasks_repo)

    listed = client.get("/tasks", params={"status": "working"})
    assert listed.status_code == 200
    assert [task["task_id"] for task in listed.json()] == ["T"]

    fetched = client.get("/tasks/T")
    assert fetched.status_code == 200
    assert fetched.json()["pane"] == "w3:pA"

    updated = client.patch("/tasks/T", json={"status": "done", "eta_min": 0, "progress": 100})
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"
    assert updated.json()["progress"] == 100

    missing = client.patch("/tasks/missing", json={"progress": 50})
    assert missing.status_code == 404


def test_router_board_and_reconcile_use_state_reconciler(tasks_repo) -> None:
    tasks_repo.upsert(
        task_id="T",
        title="Backend unit tests",
        priority=TaskPriority.P2,
        agent="codex",
        pane="w3:pA",
        status=TaskStatus.WORKING,
        eta_min=20,
        progress=50,
    )
    reconciler = FakeReconciler()
    client = _client(tasks_repo, reconciler)

    board = client.get("/tasks/board")
    assert board.status_code == 200
    assert board.json()["total_tasks"] == 1
    assert board.json()["overall_progress"] == 50.0

    reconciled = client.post("/tasks/reconcile")
    assert reconciled.status_code == 200
    assert reconciled.json()["file"]["reconciled"] == 1
    assert reconciler.calls == 1


def test_router_reports_missing_repository() -> None:
    state = SimpleNamespace(tasks_repo=None)
    app = FastAPI()
    app.include_router(build_tasks_router(lambda: state, prefix="/tasks"))
    client = TestClient(app)

    response = client.get("/tasks")

    assert response.status_code == 503
    assert response.json()["detail"] == "tasks repository unavailable"

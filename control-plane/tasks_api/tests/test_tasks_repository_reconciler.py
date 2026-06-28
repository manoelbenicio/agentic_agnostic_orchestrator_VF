from __future__ import annotations

import json

from tasks_api.models import TaskPriority, TaskStatus
from tasks_api.reconciler import TaskReconciler


def test_repository_upsert_filters_update_and_board(tasks_repo) -> None:
    tasks_repo.upsert(
        task_id="T",
        title="Backend unit tests",
        priority=TaskPriority.P2,
        agent="codex",
        pane="w3:pA",
        status=TaskStatus.WORKING,
        eta_min=60,
        progress=10,
        metadata={"phase": "qa"},
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

    assert [task.task_id for task in tasks_repo.list(status=TaskStatus.WORKING)] == ["T"]
    assert [task.task_id for task in tasks_repo.list(agent="codex", priority=TaskPriority.P1)] == ["U"]
    assert tasks_repo.get("missing") is None

    updated = tasks_repo.update("T", status=TaskStatus.DONE, eta_min=0, progress=100)

    assert updated is not None
    assert updated.status is TaskStatus.DONE
    assert updated.metadata == {"phase": "qa"}
    assert tasks_repo.update("missing", progress=50) is None
    assert tasks_repo.board() == {
        "total_tasks": 2,
        "done": 2,
        "overall_progress": 100.0,
        "total_eta_min": 0,
        "by_status": {
            "pending": {"count": 0, "eta_min": 0, "progress": 0},
            "working": {"count": 0, "eta_min": 0, "progress": 0},
            "review": {"count": 0, "eta_min": 0, "progress": 0},
            "held": {"count": 0, "eta_min": 0, "progress": 0},
            "blocked": {"count": 0, "eta_min": 0, "progress": 0},
            "orphaned": {"count": 0, "eta_min": 0, "progress": 0},
            "done": {"count": 2, "eta_min": 0, "progress": 200},
        },
    }


def test_reconciler_reads_squad_tasks_json_with_safe_defaults(tmp_path, tasks_repo) -> None:
    source = tmp_path / "squad-tasks.json"
    source.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "T",
                        "title": "Backend unit tests",
                        "priority": "invalid",
                        "agent": "codex",
                        "pane": "w3:pA",
                        "status": "unknown",
                        "eta_min": 30,
                        "progress": 25,
                        "metadata": {"herdmaster_task_id": "hm-T"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = TaskReconciler(tasks_repo, squad_tasks_path=source).reconcile_from_file()

    task = tasks_repo.get("T")
    assert result == {"reconciled": 1, "errors": [], "source": str(source)}
    assert task is not None
    assert task.priority is TaskPriority.P2
    assert task.status is TaskStatus.PENDING
    assert task.herdmaster_task_id == "hm-T"


def test_reconciler_syncs_herdmaster_state(tasks_repo) -> None:
    tasks_repo.upsert(
        task_id="T",
        title="Backend unit tests",
        priority=TaskPriority.P2,
        agent="codex",
        pane="w3:pA",
        status=TaskStatus.WORKING,
        eta_min=15,
        progress=50,
        herdmaster_task_id="hm-T",
    )

    class FakeHerdMasterClient:
        async def poll(self, envelope):
            assert envelope.task_id == "hm-T"
            return {"ok": True, "data": {"state": "done"}}

    result = TaskReconciler(tasks_repo, herdmaster_client=FakeHerdMasterClient()).sync_herdmaster_states()

    assert result == {"synced": 1, "errors": []}
    assert tasks_repo.get("T").herdmaster_state == "done"  # type: ignore[union-attr]

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[2]
if str(CONTROL_PLANE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PLANE_ROOT))

from tasks_api.models import TaskPriority, TaskRecord, TaskStatus


class InMemoryTaskRepository:
    """Unit-test double for the TaskRepository public contract."""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def list(
        self,
        *,
        status: TaskStatus | None = None,
        agent: str | None = None,
        priority: TaskPriority | None = None,
    ) -> list[TaskRecord]:
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [task for task in tasks if task.status is status]
        if agent is not None:
            tasks = [task for task in tasks if task.agent == agent]
        if priority is not None:
            tasks = [task for task in tasks if task.priority is priority]
        return sorted(tasks, key=lambda task: task.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def list_tasks(self) -> list[TaskRecord]:
        return self.list()

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def upsert(
        self,
        *,
        task_id: str,
        title: str,
        priority: TaskPriority,
        agent: str,
        pane: str,
        status: TaskStatus,
        eta_min: int,
        progress: int,
        herdmaster_task_id: str | None = None,
        herdmaster_state: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord:
        now = datetime.now(timezone.utc)
        existing = self._tasks.get(task_id)
        task = TaskRecord(
            task_id=task_id,
            title=title,
            priority=priority,
            agent=agent,
            pane=pane,
            status=status,
            eta_min=eta_min,
            progress=progress,
            herdmaster_task_id=herdmaster_task_id,
            herdmaster_state=herdmaster_state,
            metadata=metadata or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_seen_at=now,
        )
        self._tasks[task_id] = task
        return task

    def upsert_task(self, task: TaskRecord) -> None:
        self._tasks[task.task_id] = task

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        eta_min: int | None = None,
        progress: int | None = None,
        herdmaster_task_id: str | None = None,
        herdmaster_state: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord | None:
        current = self._tasks.get(task_id)
        if current is None:
            return None
        updated = replace(
            current,
            status=status if status is not None else current.status,
            eta_min=eta_min if eta_min is not None else current.eta_min,
            progress=progress if progress is not None else current.progress,
            herdmaster_task_id=herdmaster_task_id if herdmaster_task_id is not None else current.herdmaster_task_id,
            herdmaster_state=herdmaster_state if herdmaster_state is not None else current.herdmaster_state,
            metadata=metadata if metadata is not None else current.metadata,
            updated_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
        )
        self._tasks[task_id] = updated
        return updated

    def board(self) -> dict[str, Any]:
        tasks = self.list()
        total = len(tasks)
        by_status = {
            status.value: {"count": 0, "eta_min": 0, "progress": 0}
            for status in TaskStatus
        }
        for task in tasks:
            bucket = by_status[task.status.value]
            bucket["count"] += 1
            bucket["eta_min"] += task.eta_min
            bucket["progress"] += task.progress
        return {
            "total_tasks": total,
            "done": sum(1 for task in tasks if task.status is TaskStatus.DONE),
            "overall_progress": round(sum(task.progress for task in tasks) / total, 2) if total else 0.0,
            "total_eta_min": sum(task.eta_min for task in tasks if task.status is not TaskStatus.DONE),
            "by_status": by_status,
        }


@pytest.fixture
def tasks_repo() -> InMemoryTaskRepository:
    return InMemoryTaskRepository()

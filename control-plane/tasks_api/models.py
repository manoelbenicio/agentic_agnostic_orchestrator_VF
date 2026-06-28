"""OTTL task tracker domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    """Squad-task lifecycle states (mirrors squad-tasks.json status values)."""

    PENDING = "pending"
    WORKING = "working"
    REVIEW = "review"
    HELD = "held"
    BLOCKED = "blocked"
    ORPHANED = "orphaned"
    DONE = "done"


class TaskPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """A squad-task row in the OTTL trail.

    Fields mirror ``ops/squad-tasks.json`` entries augmented with
    lifecycle timestamps and HerdMaster coupling metadata.
    """

    task_id: str
    title: str
    priority: TaskPriority
    agent: str
    pane: str
    status: TaskStatus
    eta_min: int
    progress: int
    herdmaster_task_id: str | None = None
    herdmaster_state: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_seen_at: datetime | None = None

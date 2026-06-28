"""Issue tracker domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class IssueStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class IssuePriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class IssueRecord:
    issue_id: str
    tenant_id: str
    project_id: str
    title: str
    description: str | None
    status: IssueStatus
    priority: IssuePriority
    assignee_runtime: str | None
    operation_mode: str
    due_date: date | None
    metadata: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

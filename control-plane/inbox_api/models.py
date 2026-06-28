"""Domain models for inbox events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InboxEventType(StrEnum):
    """Types of inbox events."""

    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    ISSUE_CREATED = "issue_created"
    ISSUE_ASSIGNED = "issue_assigned"
    AGENT_REGISTERED = "agent_registered"
    AGENT_REMOVED = "agent_removed"
    SYSTEM = "system"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class InboxEventRecord:
    """An inbox event persisted in Postgres."""

    id: str
    tenant_id: str
    type: InboxEventType
    title: str
    message: str
    read: bool = False
    archived: bool = False
    created_at: datetime | None = None

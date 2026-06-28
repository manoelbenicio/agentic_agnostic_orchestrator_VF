"""Domain models for persisted AOP projects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ProjectStatus(StrEnum):
    """Lifecycle states for a project row."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    """A project persisted in Postgres."""

    project_id: str
    tenant_id: str
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

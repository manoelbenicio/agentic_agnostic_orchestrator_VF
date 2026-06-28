"""Models for the dynamic agent registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class AgentStatus(StrEnum):
    """Lifecycle status for a stable internal agent identity."""

    ACTIVE = "active"
    REMOVED = "removed"


class EnrollmentDecision(StrEnum):
    """Result of reconciling a discovered pane with registry policy."""

    IGNORED = "ignored"
    CANDIDATE = "candidate"
    ALREADY_ENROLLED = "already_enrolled"
    ENROLLED = "enrolled"


@dataclass(frozen=True, slots=True)
class PaneRef:
    """A Herdr pane observed in a workspace."""

    workspace_id: str
    pane_id: str
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DiscoveredPane:
    """Discovery result that does not necessarily persist anything."""

    pane: PaneRef
    decision: EnrollmentDecision
    agent: "AgentRecord | None" = None
    reason: str = ""
    wrote_to_db: bool = False


@dataclass(frozen=True, slots=True)
class AgentRecord:
    """Stable source-of-truth identity for one managed agent."""

    agent_id: str
    tenant_id: str
    label: str
    vendor: str
    role: str
    status: AgentStatus
    workspace_id: str | None = None
    pane_id: str | None = None
    stable_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Return True when this identity is currently managed."""
        return self.status == AgentStatus.ACTIVE


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0)

"""Models for ADR-001 soft coupling state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class CouplingPhase(StrEnum):
    """Current Herdr/HerdMaster coupling state."""

    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class CouplingStatus:
    """Observable coupling status exposed to app dependencies."""

    phase: CouplingPhase
    last_error: str | None = None
    attempts: int = 0
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def connected(self) -> bool:
        return self.phase == CouplingPhase.CONNECTED

    def as_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "last_error": self.last_error,
            "attempts": self.attempts,
            "checked_at": self.checked_at.isoformat(),
        }

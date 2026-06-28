"""Propagation hooks for consumers derived from the agent registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import AgentRecord

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PropagationEvent:
    """A one-action registry mutation that downstream consumers must derive from."""

    action: str
    agent: AgentRecord
    reason: str = ""


class PropagationHook(Protocol):
    """Interface implemented by ACL, allowlist, observability, and scheduler hooks."""

    name: str

    def propagate(self, event: PropagationEvent) -> None:
        """Apply a registry mutation to one downstream consumer."""


class PropagationUnavailable(RuntimeError):
    """Raised when a production propagation target is not wired."""


@dataclass(slots=True)
class RecordingPropagationHook:
    """In-memory hook useful for tests only."""

    name: str
    events: list[PropagationEvent] = field(default_factory=list)

    def propagate(self, event: PropagationEvent) -> None:
        self.events.append(event)


@dataclass(slots=True)
class _TargetPropagationHook:
    name: str
    target: Any | None = None

    def propagate(self, event: PropagationEvent) -> None:
        if self.target is None:
            message = f"{self.name} propagation target unavailable"
            log.error("registry_propagation_unavailable", extra={"target": self.name, "agent_id": event.agent.agent_id})
            raise PropagationUnavailable(message)
        method_name = f"propagate_{event.action.replace('.', '_')}"
        method = getattr(self.target, method_name, None) or getattr(self.target, "propagate", None)
        if method is None:
            message = f"{self.name} propagation target does not implement {method_name} or propagate"
            log.error("registry_propagation_unsupported", extra={"target": self.name, "agent_id": event.agent.agent_id})
            raise PropagationUnavailable(message)
        method(event)


class AclPropagationHook(_TargetPropagationHook):
    """Propagate registry changes to a real ACL target."""

    def __init__(self, target: Any | None = None) -> None:
        super().__init__("acl", target)


class AllowlistPropagationHook(_TargetPropagationHook):
    """Propagate registry changes to a real allowlist/source-of-truth target."""

    def __init__(self, target: Any | None = None) -> None:
        super().__init__("allowlist", target)


class ObservabilityPropagationHook(_TargetPropagationHook):
    """Propagate registry changes to a real observability target."""

    def __init__(self, target: Any | None = None) -> None:
        super().__init__("observability", target)


class SchedulerPropagationHook(_TargetPropagationHook):
    """Propagate registry changes to a real scheduler target."""

    def __init__(self, target: Any | None = None) -> None:
        super().__init__("scheduler", target)


@dataclass(slots=True)
class CompositePropagationHook:
    """Fan out each registry mutation to all registered hooks."""

    hooks: tuple[PropagationHook, ...]
    name: str = "composite"

    @classmethod
    def default(cls) -> "CompositePropagationHook":
        """Return the default propagation set required by the registry capability."""
        return cls(
            (
                AclPropagationHook(),
                AllowlistPropagationHook(),
                ObservabilityPropagationHook(),
                SchedulerPropagationHook(),
            )
        )

    def propagate(self, event: PropagationEvent) -> None:
        for hook in self.hooks:
            hook.propagate(event)

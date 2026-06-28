"""Abstract interfaces for dispatch executors and agent runtime adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from typing import Any

from .models import (
    AdapterMetering,
    AgentState,
    LifecycleEvent,
    RuntimeRef,
    TaskEnvelope,
)


class Executor(ABC):
    """Mode-specific task executor behind the unified task/event contract."""

    @abstractmethod
    def dispatch(self, task: TaskEnvelope) -> AsyncIterator[LifecycleEvent]:
        """Dispatch a task and yield normalized lifecycle events."""
        raise NotImplementedError


class AgentRuntimeAdapter(ABC):
    """Agnostic adapter for controlling a vendor CLI runtime."""

    @abstractmethod
    async def spawn(self, task: TaskEnvelope) -> RuntimeRef:
        """Start a runtime process/session for a task and return its reference."""
        raise NotImplementedError

    @abstractmethod
    async def send(self, runtime: RuntimeRef, payload: str) -> None:
        """Send input to a running agent runtime."""
        raise NotImplementedError

    @abstractmethod
    async def read_state(self, runtime: RuntimeRef) -> AgentState:
        """Read the normalized runtime state: idle, working, blocked, done, or unknown."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self, runtime: RuntimeRef) -> None:
        """Stop a running runtime session."""
        raise NotImplementedError

    @abstractmethod
    async def restore(self, runtime: RuntimeRef) -> RuntimeRef:
        """Restore or reconnect to a prior runtime session."""
        raise NotImplementedError

    @abstractmethod
    async def meter(
        self,
        runtime: RuntimeRef,
        usage_hint: Mapping[str, Any] | None = None,
    ) -> AdapterMetering:
        """Return billing usage units such as tokens or seat-seconds."""
        raise NotImplementedError


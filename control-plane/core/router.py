"""Operation-mode router for selecting task executors."""

from __future__ import annotations

from collections.abc import Mapping

from .interfaces import Executor
from .models import OperationMode, TaskEnvelope


class ExecutorNotRegisteredError(LookupError):
    """Raised when no executor has been registered for an operation mode."""


class ModeRouter:
    """Resolve the executor that must handle a task's selected operation mode."""

    def __init__(self, executors: Mapping[OperationMode | str, Executor]) -> None:
        """Create a router from terminal/socket modes to executor instances."""
        self._executors = {
            OperationMode(mode): executor for mode, executor in executors.items()
        }

    def executor_for(self, mode_or_task: OperationMode | str | TaskEnvelope) -> Executor:
        """Return the executor registered for an operation mode or task envelope."""
        mode = (
            mode_or_task.operation_mode
            if isinstance(mode_or_task, TaskEnvelope)
            else OperationMode(mode_or_task)
        )
        try:
            return self._executors[mode]
        except KeyError as exc:
            raise ExecutorNotRegisteredError(
                f"No executor registered for operation_mode={mode.value!r}"
            ) from exc

    def route(self, task: TaskEnvelope) -> Executor:
        """Return the executor that should dispatch the supplied task."""
        return self.executor_for(task)


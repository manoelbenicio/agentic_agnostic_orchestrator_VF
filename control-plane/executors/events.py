"""Helpers for emitting normalized lifecycle events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core import LifecycleEvent, LifecycleStatus, OperationMode, TaskEnvelope


def lifecycle_event(
    task: TaskEnvelope,
    status: LifecycleStatus,
    *,
    runtime: str | None = None,
    trace_id: str | None = None,
    cost_refs: tuple[str, ...] = (),
    message: str | None = None,
    details: Mapping[str, Any] | None = None,
    operation_mode: OperationMode | None = None,
) -> LifecycleEvent:
    """Create a normalized event for either executor."""
    return LifecycleEvent(
        task_id=task.task_id,
        tenant_id=task.tenant_id,
        project_id=task.project_id,
        status=status,
        operation_mode=operation_mode or task.operation_mode,
        runtime=runtime or task.assignee_runtime,
        trace_id=trace_id,
        cost_refs=cost_refs,
        message=message,
        details=dict(details or {}),
    )


def failure_event(
    task: TaskEnvelope,
    exc: BaseException,
    *,
    runtime: str | None = None,
) -> LifecycleEvent:
    """Create a failed lifecycle event from an exception."""
    return lifecycle_event(
        task,
        LifecycleStatus.FAILED,
        runtime=runtime,
        message=str(exc),
        details={"error_type": type(exc).__name__},
    )


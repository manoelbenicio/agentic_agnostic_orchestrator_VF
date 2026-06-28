from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from pydantic import ValidationError

from core import (
    AgentRuntimeAdapter,
    AgentState,
    Executor,
    ExecutorNotRegisteredError,
    LifecycleEvent,
    LifecycleStatus,
    ModeRouter,
    OperationMode,
    RuntimeRef,
    TaskBudget,
    TaskEnvelope,
)


class FakeExecutor(Executor):
    def dispatch(self, task: TaskEnvelope) -> AsyncIterator[LifecycleEvent]:
        async def events() -> AsyncIterator[LifecycleEvent]:
            yield LifecycleEvent(
                task_id=task.task_id,
                tenant_id=task.tenant_id,
                project_id=task.project_id,
                status=LifecycleStatus.QUEUED,
                operation_mode=task.operation_mode,
                runtime=task.assignee_runtime,
            )

        return events()


class FakeAdapter(AgentRuntimeAdapter):
    async def spawn(self, task: TaskEnvelope) -> RuntimeRef:
        return RuntimeRef(
            runtime_id=task.task_id,
            vendor=task.assignee_runtime,
            mode=task.operation_mode,
        )

    async def send(self, runtime: RuntimeRef, payload: str) -> None:
        return None

    async def read_state(self, runtime: RuntimeRef) -> AgentState:
        return AgentState.IDLE

    async def stop(self, runtime: RuntimeRef) -> None:
        return None

    async def restore(self, runtime: RuntimeRef) -> RuntimeRef:
        return runtime

    async def meter(self, runtime: RuntimeRef, usage_hint=None):
        from core import AdapterMetering

        return AdapterMetering(runtime_id=runtime.runtime_id)


def make_task(operation_mode: OperationMode | str = OperationMode.TERMINAL) -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-1",
        tenant_id="tenant-1",
        project_id="project-1",
        assignee_runtime="codex",
        prompt="Implement the contract.",
        budget=TaskBudget(max_tokens=1000, seat_seconds=300),
        credential_ref="seat://tenant-1/codex/default",
        operation_mode=operation_mode,
    )


def test_task_envelope_accepts_required_contract_fields() -> None:
    task = make_task("terminal")

    assert task.operation_mode is OperationMode.TERMINAL
    assert task.budget.max_tokens == 1000
    assert task.callbacks.on_event == ()


def test_task_envelope_rejects_unknown_mode_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        make_task("batch")

    with pytest.raises(ValidationError):
        TaskEnvelope(
            task_id="task-1",
            tenant_id="tenant-1",
            project_id="project-1",
            assignee_runtime="codex",
            prompt="No extra fields.",
            credential_ref="seat://tenant-1/codex/default",
            operation_mode="socket",
            unexpected=True,
        )


def test_lifecycle_event_uses_normalized_status_and_aware_timestamp() -> None:
    event = LifecycleEvent(
        task_id="task-1",
        tenant_id="tenant-1",
        project_id="project-1",
        status="done",
        operation_mode="socket",
        runtime="gemini",
        cost_refs=("cost-1",),
    )

    assert event.status is LifecycleStatus.DONE
    assert event.occurred_at.tzinfo is not None
    assert event.cost_refs == ("cost-1",)

    with pytest.raises(ValidationError):
        LifecycleEvent(
            task_id="task-1",
            tenant_id="tenant-1",
            project_id="project-1",
            status="running",
            occurred_at=datetime(2026, 6, 26, 12, 0, 0),
            operation_mode="socket",
            runtime="gemini",
        )


def test_mode_router_returns_executor_for_task_mode() -> None:
    terminal = FakeExecutor()
    socket = FakeExecutor()
    router = ModeRouter(
        {
            OperationMode.TERMINAL: terminal,
            OperationMode.SOCKET: socket,
        }
    )

    assert router.route(make_task("terminal")) is terminal
    assert router.executor_for("socket") is socket


def test_mode_router_raises_when_executor_missing() -> None:
    router = ModeRouter({OperationMode.TERMINAL: FakeExecutor()})

    with pytest.raises(ExecutorNotRegisteredError):
        router.route(make_task("socket"))


def test_agent_runtime_adapter_interface_can_be_implemented() -> None:
    adapter = FakeAdapter()

    assert isinstance(adapter, AgentRuntimeAdapter)


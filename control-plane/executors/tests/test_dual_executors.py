from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from decimal import Decimal
from typing import Any

from core import (
    AdapterMetering,
    AgentRuntimeAdapter,
    AgentState,
    Executor,
    LifecycleEvent,
    LifecycleStatus,
    OperationMode,
    RuntimeRef,
    TaskEnvelope,
)
from executors import SocketExecutor, TerminalExecutor, build_mode_router


class FakeRuntimeAdapter(AgentRuntimeAdapter):
    def __init__(self, state: AgentState = AgentState.DONE) -> None:
        self.state = state
        self.sent: list[str] = []

    async def spawn(self, task: TaskEnvelope) -> RuntimeRef:
        return RuntimeRef(
            runtime_id=f"pane-{task.task_id}",
            vendor=task.assignee_runtime,
            mode=OperationMode.TERMINAL,
            native_ref="pane-1",
        )

    async def send(self, runtime: RuntimeRef, payload: str) -> None:
        self.sent.append(payload)

    async def read_state(self, runtime: RuntimeRef) -> AgentState:
        return self.state

    async def stop(self, runtime: RuntimeRef) -> None:
        return None

    async def restore(self, runtime: RuntimeRef) -> RuntimeRef:
        return runtime

    async def meter(
        self,
        runtime: RuntimeRef,
        usage_hint: Mapping[str, Any] | None = None,
    ) -> AdapterMetering:
        return AdapterMetering(
            runtime_id=runtime.runtime_id,
            usage_units={"seat_seconds": Decimal("3")},
            cost_refs=("cost-terminal",),
        )


class FakeQueueClient:
    def __init__(self, final_state: str = "done") -> None:
        self.final_state = final_state
        self.calls: list[str] = []

    async def enqueue(self, task: TaskEnvelope) -> Mapping[str, Any]:
        self.calls.append("enqueue")
        return {"id": task.task_id, "state": "queued"}

    async def claim(self, task: TaskEnvelope) -> Mapping[str, Any]:
        self.calls.append("claim")
        return {"id": task.task_id, "state": "assigned", "assigned_to": task.assignee_runtime}

    async def mark_running(self, task: TaskEnvelope) -> Mapping[str, Any]:
        self.calls.append("mark_running")
        return {"id": task.task_id, "state": "in_progress"}

    async def poll(self, task: TaskEnvelope) -> Mapping[str, Any]:
        self.calls.append("poll")
        return {"id": task.task_id, "state": self.final_state}


def task(mode: OperationMode | str) -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-1",
        tenant_id="tenant-1",
        project_id="project-1",
        assignee_runtime="codex",
        prompt="do the work",
        credential_ref="seat://tenant-1/codex/default",
        operation_mode=mode,
    )


async def collect(events: AsyncIterator[LifecycleEvent]) -> list[LifecycleEvent]:
    return [event async for event in events]


def test_terminal_executor_implements_core_executor_and_emits_schema() -> None:
    async def scenario() -> None:
        adapter = FakeRuntimeAdapter()
        executor = TerminalExecutor(adapter)

        assert isinstance(executor, Executor)

        events = await collect(executor.dispatch(task("terminal")))

        assert [event.status for event in events] == [
            LifecycleStatus.QUEUED,
            LifecycleStatus.CLAIMED,
            LifecycleStatus.RUNNING,
            LifecycleStatus.DONE,
        ]
        assert {event.operation_mode for event in events} == {OperationMode.TERMINAL}
        assert events[-1].cost_refs == ("cost-terminal",)
        assert adapter.sent == ["do the work"]

    asyncio.run(scenario())


def test_terminal_executor_maps_blocked_runtime_state() -> None:
    async def scenario() -> None:
        executor = TerminalExecutor(FakeRuntimeAdapter(state=AgentState.BLOCKED))

        events = await collect(executor.dispatch(task("terminal")))

        assert events[-1].status is LifecycleStatus.BLOCKED
        assert all(isinstance(event, LifecycleEvent) for event in events)

    asyncio.run(scenario())


def test_socket_executor_implements_core_executor_and_emits_same_schema() -> None:
    async def scenario() -> None:
        queue = FakeQueueClient(final_state="done")
        executor = SocketExecutor(queue, max_polls=1)

        assert isinstance(executor, Executor)

        events = await collect(executor.dispatch(task("socket")))

        assert [event.status for event in events] == [
            LifecycleStatus.QUEUED,
            LifecycleStatus.CLAIMED,
            LifecycleStatus.RUNNING,
            LifecycleStatus.DONE,
        ]
        assert {event.operation_mode for event in events} == {OperationMode.SOCKET}
        assert queue.calls == ["enqueue", "claim", "mark_running", "poll"]
        assert all(isinstance(event, LifecycleEvent) for event in events)

    asyncio.run(scenario())


def test_socket_executor_maps_failed_and_blocked_queue_states() -> None:
    async def scenario() -> None:
        failed_events = await collect(SocketExecutor(FakeQueueClient("failed")).dispatch(task("socket")))
        blocked_events = await collect(SocketExecutor(FakeQueueClient("blocked")).dispatch(task("socket")))

        assert failed_events[-1].status is LifecycleStatus.FAILED
        assert blocked_events[-1].status is LifecycleStatus.BLOCKED

    asyncio.run(scenario())


def test_build_mode_router_links_terminal_and_socket_executors() -> None:
    terminal = TerminalExecutor(FakeRuntimeAdapter())
    socket = SocketExecutor(FakeQueueClient())
    router = build_mode_router(terminal, socket)

    assert router.route(task("terminal")) is terminal
    assert router.route(task("socket")) is socket

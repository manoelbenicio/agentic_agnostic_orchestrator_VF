"""Terminal-mode executor backed by an AgentRuntimeAdapter / Herdr adapter."""

from __future__ import annotations

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

from .events import failure_event, lifecycle_event


class HerdrRuntimeAdapter(AgentRuntimeAdapter):
    """Adapter facade over HerdMaster's existing HerdrAdapter."""

    def __init__(self, herdr_adapter: Any | None = None) -> None:
        """Create a facade around a HerdMaster HerdrAdapter instance."""
        if herdr_adapter is None:
            try:
                from herdmaster.herdr.adapter import HerdrAdapter
            except ImportError as exc:
                raise RuntimeError("HerdMaster HerdrAdapter is not importable") from exc
            herdr_adapter = HerdrAdapter()
        self.herdr_adapter = herdr_adapter

    async def spawn(self, task: TaskEnvelope) -> RuntimeRef:
        """Use the task assignee as the Herdr pane/agent reference."""
        pane_id = task.assignee_runtime
        if hasattr(self.herdr_adapter, "spawn_agent"):
            await self.herdr_adapter.spawn_agent(pane_id, task.prompt)
        return RuntimeRef(
            runtime_id=pane_id,
            vendor=task.assignee_runtime,
            mode=OperationMode.TERMINAL,
            native_ref=pane_id,
        )

    async def send(self, runtime: RuntimeRef, payload: str) -> None:
        """Send text to the Herdr pane for the runtime."""
        await self.herdr_adapter.pane_send(runtime.native_ref or runtime.runtime_id, payload)

    async def read_state(self, runtime: RuntimeRef) -> AgentState:
        """Read and normalize Herdr agent state."""
        agent_id = runtime.native_ref or runtime.runtime_id
        if hasattr(self.herdr_adapter, "agent_list"):
            for agent in await self.herdr_adapter.agent_list():
                if getattr(agent, "id", None) == agent_id or getattr(agent, "pane_id", None) == agent_id:
                    return _map_agent_state(str(getattr(agent, "state", "unknown")))
        return AgentState.UNKNOWN

    async def stop(self, runtime: RuntimeRef) -> None:
        """Close the underlying Herdr pane when the adapter supports it."""
        pane_id = runtime.native_ref or runtime.runtime_id
        if hasattr(self.herdr_adapter, "pane_close"):
            await self.herdr_adapter.pane_close(pane_id)

    async def restore(self, runtime: RuntimeRef) -> RuntimeRef:
        """Return the existing Herdr runtime reference."""
        return runtime

    async def meter(
        self,
        runtime: RuntimeRef,
        usage_hint: Mapping[str, Any] | None = None,
    ) -> AdapterMetering:
        """Report seat-utilization units for subscription-seat terminal runs."""
        hint = usage_hint or {}
        seat_seconds = Decimal(str(hint.get("seat_seconds", 0)))
        return AdapterMetering(
            runtime_id=runtime.runtime_id,
            usage_units={"seat_seconds": seat_seconds},
        )


class TerminalExecutor(Executor):
    """Executor for terminal/multiplexer tasks."""

    def __init__(self, adapter: AgentRuntimeAdapter | None = None) -> None:
        """Create a terminal executor with an injectable runtime adapter."""
        self.adapter = adapter or HerdrRuntimeAdapter()

    def dispatch(self, task: TaskEnvelope) -> AsyncIterator[LifecycleEvent]:
        """Dispatch a terminal-mode task and yield normalized events."""

        async def events() -> AsyncIterator[LifecycleEvent]:
            runtime: RuntimeRef | None = None
            try:
                yield lifecycle_event(
                    task,
                    LifecycleStatus.QUEUED,
                    operation_mode=OperationMode.TERMINAL,
                )
                runtime = await self.adapter.spawn(task)
                yield lifecycle_event(
                    task,
                    LifecycleStatus.CLAIMED,
                    runtime=runtime.runtime_id,
                    details={"runtime_ref": runtime.model_dump(mode="json")},
                    operation_mode=OperationMode.TERMINAL,
                )
                await self.adapter.send(runtime, task.prompt)
                yield lifecycle_event(
                    task,
                    LifecycleStatus.RUNNING,
                    runtime=runtime.runtime_id,
                    operation_mode=OperationMode.TERMINAL,
                )

                state = await self.adapter.read_state(runtime)
                if state is AgentState.BLOCKED:
                    yield lifecycle_event(
                        task,
                        LifecycleStatus.BLOCKED,
                        runtime=runtime.runtime_id,
                        operation_mode=OperationMode.TERMINAL,
                    )
                    return

                metering = await self.adapter.meter(runtime)
                yield lifecycle_event(
                    task,
                    LifecycleStatus.DONE,
                    runtime=runtime.runtime_id,
                    cost_refs=metering.cost_refs,
                    details={
                        "agent_state": state.value,
                        "metering": metering.model_dump(mode="json"),
                    },
                    operation_mode=OperationMode.TERMINAL,
                )
            except Exception as exc:
                yield failure_event(
                    task,
                    exc,
                    runtime=runtime.runtime_id if runtime is not None else None,
                )

        return events()


def _map_agent_state(state: str) -> AgentState:
    normalized = state.lower()
    if normalized in {"idle", "ready"}:
        return AgentState.IDLE
    if normalized in {"working", "running", "busy", "in_progress"}:
        return AgentState.WORKING
    if normalized in {"blocked", "waiting"}:
        return AgentState.BLOCKED
    if normalized in {"done", "complete", "completed"}:
        return AgentState.DONE
    return AgentState.UNKNOWN


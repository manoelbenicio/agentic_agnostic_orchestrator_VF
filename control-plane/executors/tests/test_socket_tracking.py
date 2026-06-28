"""Tests for SocketExecutor completion tracking and FinOps usage surfacing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

from core import LifecycleEvent, LifecycleStatus, OperationMode, TaskBudget, TaskEnvelope
from executors import SocketExecutor


class ProgressiveQueueClient:
    """Returns non-terminal states for the first N polls, then 'done' with usage."""

    def __init__(self, running_polls: int, usage: Mapping[str, Any] | None = None) -> None:
        self.running_polls = running_polls
        self.usage = usage
        self.poll_count = 0

    async def enqueue(self, task: TaskEnvelope) -> Mapping[str, Any]:
        return {"id": task.task_id, "state": "queued"}

    async def claim(self, task: TaskEnvelope) -> Mapping[str, Any]:
        return {"id": task.task_id, "state": "assigned"}

    async def mark_running(self, task: TaskEnvelope) -> Mapping[str, Any]:
        return {"id": task.task_id, "state": "in_progress"}

    async def poll(self, task: TaskEnvelope) -> Mapping[str, Any]:
        self.poll_count += 1
        if self.poll_count <= self.running_polls:
            return {"id": task.task_id, "state": "in_progress"}
        record: dict[str, Any] = {"id": task.task_id, "state": "done"}
        if self.usage:
            record["usage"] = dict(self.usage)
        return record


def _task(*, timeout_seconds: int | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-track",
        tenant_id="tenant-1",
        project_id="project-1",
        assignee_runtime="codex",
        prompt="do the work",
        credential_ref="seat://tenant-1/codex/default",
        operation_mode=OperationMode.SOCKET,
        budget=TaskBudget(timeout_seconds=timeout_seconds),
    )


async def _collect(events: AsyncIterator[LifecycleEvent]) -> list[LifecycleEvent]:
    return [event async for event in events]


def test_socket_tracks_until_terminal_with_timeout_budget() -> None:
    async def scenario() -> None:
        queue = ProgressiveQueueClient(running_polls=3)
        executor = SocketExecutor(queue, poll_interval_s=0.0, max_polls=1)
        events = await _collect(executor.dispatch(_task(timeout_seconds=5)))

        # With a timeout budget, it must keep polling past max_polls=1 until 'done'.
        assert events[-1].status is LifecycleStatus.DONE
        assert queue.poll_count == 4  # 3 in_progress + 1 done

    asyncio.run(scenario())


def test_socket_surfaces_token_usage_into_finops_details() -> None:
    async def scenario() -> None:
        usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "input_token_price_usd": "0.000001",
            "output_token_price_usd": "0.000002",
            "model": "gpt-x",
        }
        queue = ProgressiveQueueClient(running_polls=0, usage=usage)
        executor = SocketExecutor(queue, poll_interval_s=0.0, max_polls=1)
        events = await _collect(executor.dispatch(_task()))

        done = events[-1]
        assert done.status is LifecycleStatus.DONE
        assert done.details["finops"]["token"]["model"] == "gpt-x"

    asyncio.run(scenario())


def test_socket_without_timeout_keeps_single_poll_default() -> None:
    async def scenario() -> None:
        # No timeout budget and max_polls=1 -> exactly one poll (backward compatible).
        queue = ProgressiveQueueClient(running_polls=5)
        executor = SocketExecutor(queue, poll_interval_s=0.0, max_polls=1)
        events = await _collect(executor.dispatch(_task()))

        assert queue.poll_count == 1
        assert events[-1].status is LifecycleStatus.DONE  # fallback "accepted" DONE

    asyncio.run(scenario())

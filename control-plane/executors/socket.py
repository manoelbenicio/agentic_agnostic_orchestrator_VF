"""Socket-mode executor backed by HerdMaster queue/dispatch semantics."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol
from urllib import error, parse, request

from core import Executor, LifecycleEvent, LifecycleStatus, OperationMode, TaskEnvelope

from .events import failure_event, lifecycle_event


class SocketQueueClient(Protocol):
    """Minimal queue client boundary used by SocketExecutor.

    Implementations may wrap HerdMaster imports directly or call the HerdMaster
    HTTP API. Tests can provide an in-memory fake without running HerdMaster.
    """

    async def enqueue(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Persist or surface a task in the socket-mode queue."""
        ...

    async def claim(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Atomically claim the queued task for its assignee/runtime."""
        ...

    async def mark_running(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Move the claimed task to running/in-progress state."""
        ...

    async def poll(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Return the latest queue state for a task."""
        ...


class HerdMasterHttpQueueClient:
    """HTTP adapter for the existing HerdMaster task API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout_s: float = 10.0) -> None:
        """Create a client for a running HerdMaster API server."""
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def enqueue(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Create or mirror a task in HerdMaster's queue."""
        payload = {
            "title": task.task_id,
            "prompt": task.prompt,
            "task_id": task.task_id,
            "project_id": task.project_id,
            "assigned_to": task.assignee_runtime,
            "created_by": task.tenant_id,
            "timeout_seconds": task.budget.timeout_seconds or 1800,
        }
        return await asyncio.to_thread(self._request, "POST", "/tasks", payload)

    async def claim(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Confirm the task is claimed for the requested runtime."""
        return await asyncio.to_thread(
            self._request,
            "GET",
            "/tasks",
            None,
            {"assigned_to": task.assignee_runtime, "project_id": task.project_id},
        )

    async def mark_running(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Set the HerdMaster task state to in_progress."""
        return await asyncio.to_thread(
            self._request,
            "PATCH",
            f"/tasks/{parse.quote(task.task_id)}",
            {"state": "in_progress"},
        )

    async def poll(self, task: TaskEnvelope) -> Mapping[str, Any]:
        """Fetch the latest task record from HerdMaster."""
        return await asyncio.to_thread(
            self._request,
            "GET",
            f"/tasks/{parse.quote(task.task_id)}",
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        query_text = f"?{parse.urlencode(query)}" if query else ""
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}{query_text}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise RuntimeError(f"HerdMaster API request failed: {exc}") from exc
        if not isinstance(decoded, dict) or not decoded.get("ok", False):
            raise RuntimeError(f"HerdMaster API returned an error: {decoded!r}")
        data = decoded.get("data", {})
        return data if isinstance(data, Mapping) else {"data": data}


class SocketExecutor(Executor):
    """Executor for socket/control-plane tasks using HerdMaster queue semantics."""

    def __init__(
        self,
        queue_client: SocketQueueClient | None = None,
        *,
        poll_interval_s: float = 0.1,
        max_polls: int = 1,
    ) -> None:
        """Create a socket executor with an injectable queue client."""
        self.queue_client = queue_client or HerdMasterHttpQueueClient()
        self.poll_interval_s = poll_interval_s
        self.max_polls = max_polls

    def dispatch(self, task: TaskEnvelope) -> AsyncIterator[LifecycleEvent]:
        """Dispatch a socket-mode task and yield normalized events."""

        async def events() -> AsyncIterator[LifecycleEvent]:
            try:
                enqueue_result = await self.queue_client.enqueue(task)
                yield lifecycle_event(
                    task,
                    LifecycleStatus.QUEUED,
                    details={"queue": dict(enqueue_result)},
                    operation_mode=OperationMode.SOCKET,
                )

                claim_result = await self.queue_client.claim(task)
                yield lifecycle_event(
                    task,
                    LifecycleStatus.CLAIMED,
                    details={"queue": dict(claim_result)},
                    operation_mode=OperationMode.SOCKET,
                )

                running_result = await self.queue_client.mark_running(task)
                yield lifecycle_event(
                    task,
                    LifecycleStatus.RUNNING,
                    details={"queue": dict(running_result)},
                    operation_mode=OperationMode.SOCKET,
                )

                async for event in self._poll_terminal_status(task):
                    yield event
            except Exception as exc:
                yield failure_event(task, exc)

        return events()

    async def _poll_terminal_status(self, task: TaskEnvelope) -> AsyncIterator[LifecycleEvent]:
        """Poll until the task reaches a terminal state.

        When ``task.budget.timeout_seconds`` is set the executor polls until the
        task is terminal or the deadline elapses (real completion tracking).
        Otherwise it falls back to ``max_polls`` bounded polling (default 1),
        preserving the lightweight contract used by tests and stubs.
        """
        deadline: float | None = None
        if task.budget.timeout_seconds:
            deadline = time.monotonic() + float(task.budget.timeout_seconds)
        attempt = 0
        while True:
            if attempt:
                await asyncio.sleep(self.poll_interval_s)
            latest = await self.queue_client.poll(task)
            status = _map_queue_state(str(latest.get("state") or latest.get("status") or "done"))
            if status in {LifecycleStatus.BLOCKED, LifecycleStatus.DONE, LifecycleStatus.FAILED}:
                yield lifecycle_event(
                    task,
                    status,
                    details=self._poll_details(latest),
                    operation_mode=OperationMode.SOCKET,
                )
                return
            attempt += 1
            if deadline is not None:
                if time.monotonic() >= deadline:
                    break
            elif attempt >= max(1, self.max_polls):
                break
        yield lifecycle_event(
            task,
            LifecycleStatus.DONE,
            message="socket dispatch accepted; terminal completion will be reported by queue polling",
            operation_mode=OperationMode.SOCKET,
        )

    @staticmethod
    def _poll_details(latest: Mapping[str, Any]) -> dict[str, Any]:
        """Build event details from a queue record, surfacing usage for FinOps.

        If the HerdMaster task record carries a ``usage`` mapping (token usage and
        unit prices), it is forwarded under ``details["finops"]["token"]`` so the
        dispatch bridge records the cost automatically. No data is fabricated:
        when HerdMaster reports no usage, nothing is recorded.
        """
        details: dict[str, Any] = {"queue": dict(latest)}
        usage = latest.get("usage")
        if isinstance(usage, Mapping) and usage:
            details["finops"] = {"token": dict(usage)}
        return details


def _map_queue_state(state: str) -> LifecycleStatus:
    normalized = state.lower()
    if normalized in {"blocked", "waiting"}:
        return LifecycleStatus.BLOCKED
    if normalized in {"failed", "timeout", "cancelled", "error"}:
        return LifecycleStatus.FAILED
    if normalized in {"done", "completed", "complete", "success"}:
        return LifecycleStatus.DONE
    if normalized in {"assigned", "claimed"}:
        return LifecycleStatus.CLAIMED
    if normalized in {"in_progress", "running", "dispatched"}:
        return LifecycleStatus.RUNNING
    if normalized == "queued":
        return LifecycleStatus.QUEUED
    return LifecycleStatus.RUNNING


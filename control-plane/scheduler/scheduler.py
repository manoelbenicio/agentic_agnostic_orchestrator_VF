"""Quota-aware admission control and dispatch scheduling."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core import TaskEnvelope

from .backoff import BackoffPolicy
from .quota import QuotaLedger


class AdmissionStatus(StrEnum):
    """Admission decision outcome."""

    DISPATCH = "dispatch"
    QUEUED = "queued"
    WAITING_ON_QUOTA = "waiting_on_quota"
    WAITING_ON_CONCURRENCY = "waiting_on_concurrency"


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Decision returned by quota-aware admission control."""

    status: AdmissionStatus
    reason: str
    vendor: str
    estimated_burn_seconds: int

    @property
    def admitted(self) -> bool:
        """True when the task may dispatch now."""
        return self.status is AdmissionStatus.DISPATCH


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    """Queued task plus scheduling metadata."""

    task: TaskEnvelope
    vendor: str
    estimated_burn_seconds: int
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


class VendorRateLimitError(RuntimeError):
    """Raised by dispatchers on vendor 429/503 responses."""

    def __init__(self, status_code: int, message: str = "vendor rate limited") -> None:
        """Create a rate-limit error from an HTTP-like status code."""
        super().__init__(message)
        self.status_code = status_code


DispatchCallable = Callable[[TaskEnvelope], Awaitable[Any]]


class QuotaAwareScheduler:
    """Admission controller for shared vendor quota and local concurrency."""

    def __init__(
        self,
        quota: QuotaLedger,
        *,
        max_concurrent: int = 20,
        backoff: BackoffPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Create a scheduler with shared quota and concurrency limits."""
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.quota = quota
        self.max_concurrent = max_concurrent
        self.backoff = backoff or BackoffPolicy()
        self.sleep = sleep
        self.running_count = 0
        self.queue: deque[ScheduledTask] = deque()
        self.backoff_log: list[float] = []

    def admit(
        self,
        task: TaskEnvelope,
        *,
        vendor: str | None = None,
        estimated_burn_seconds: int | None = None,
    ) -> AdmissionDecision:
        """Admit or queue a task without failing on quota exhaustion."""
        task_vendor = vendor or task.assignee_runtime
        estimate = estimated_burn_seconds or task.budget.seat_seconds or 0
        if self.running_count >= self.max_concurrent:
            return self._queue(
                task,
                task_vendor,
                estimate,
                AdmissionStatus.WAITING_ON_CONCURRENCY,
                "concurrency ceiling reached",
            )
        if not self.quota.has_headroom(task_vendor, estimate):
            return self._queue(
                task,
                task_vendor,
                estimate,
                AdmissionStatus.WAITING_ON_QUOTA,
                "shared quota exhausted",
            )
        self.quota.reserve(task_vendor, estimate)
        return AdmissionDecision(
            status=AdmissionStatus.DISPATCH,
            reason="admitted",
            vendor=task_vendor,
            estimated_burn_seconds=estimate,
        )

    async def dispatch_with_backoff(
        self,
        task: TaskEnvelope,
        dispatch: DispatchCallable,
        *,
        attempts: int = 3,
    ) -> Any:
        """Dispatch a task, retrying 429/503 with exponential backoff and jitter."""
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        last_error: VendorRateLimitError | None = None
        self.running_count += 1
        try:
            for attempt in range(1, attempts + 1):
                try:
                    return await dispatch(task)
                except VendorRateLimitError as exc:
                    if exc.status_code not in {429, 503}:
                        raise
                    last_error = exc
                    if attempt == attempts:
                        break
                    delay = self.backoff.delay(attempt)
                    self.backoff_log.append(delay)
                    await self.sleep(delay)
            assert last_error is not None
            self._queue(
                task,
                task.assignee_runtime,
                task.budget.seat_seconds or 0,
                AdmissionStatus.QUEUED,
                f"rate limited after {attempts} attempts",
            )
            return None
        finally:
            self.running_count -= 1

    def complete_one(self) -> None:
        """Release one local concurrency slot."""
        self.running_count = max(0, self.running_count - 1)

    def _queue(
        self,
        task: TaskEnvelope,
        vendor: str,
        estimated_burn_seconds: int,
        status: AdmissionStatus,
        reason: str,
    ) -> AdmissionDecision:
        self.queue.append(
            ScheduledTask(
                task=task,
                vendor=vendor,
                estimated_burn_seconds=estimated_burn_seconds,
                reason=reason,
            )
        )
        return AdmissionDecision(
            status=status,
            reason=reason,
            vendor=vendor,
            estimated_burn_seconds=estimated_burn_seconds,
        )


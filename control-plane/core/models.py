"""Pydantic models for the AOP task envelope and lifecycle event stream."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OperationMode(StrEnum):
    """Execution mode selected per task and honored by the dispatcher."""

    TERMINAL = "terminal"
    SOCKET = "socket"


class LifecycleStatus(StrEnum):
    """Normalized lifecycle statuses emitted by all executors."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


class AgentState(StrEnum):
    """Normalized runtime state returned by agent adapters."""

    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    DONE = "done"
    UNKNOWN = "unknown"


class TaskBudget(BaseModel):
    """Optional task budget constraints shared by all executors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tokens: int | None = Field(default=None, ge=0)
    max_cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    timeout_seconds: int | None = Field(default=None, ge=1)
    seat_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCallbacks(BaseModel):
    """Callback targets used by control-plane consumers for task updates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    on_event: tuple[str, ...] = Field(default_factory=tuple)
    on_complete: tuple[str, ...] = Field(default_factory=tuple)
    on_failure: tuple[str, ...] = Field(default_factory=tuple)


class TaskEnvelope(BaseModel):
    """Typed task envelope consumed unchanged by Terminal and Socket executors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    assignee_runtime: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    budget: TaskBudget = Field(default_factory=TaskBudget)
    credential_ref: str = Field(min_length=1)
    operation_mode: OperationMode
    callbacks: TaskCallbacks = Field(default_factory=TaskCallbacks)
    # Optional attribution fields used for FinOps cost recording during dispatch.
    # Defaulted for backward compatibility; when absent, agent_id falls back to
    # assignee_runtime and issue_id falls back to "issue-default".
    issue_id: str | None = Field(default=None, min_length=1)
    agent_id: str | None = Field(default=None, min_length=1)
    # Account currently leased to this task's runtime (rotation — doc 36/ADR-009).
    # When set and rotation is enabled, dispatch can rotate to the next account
    # on token exhaustion. None = rotation skipped (no current-account mapping).
    account_id: str | None = Field(default=None, min_length=1)


class RuntimeRef(BaseModel):
    """Stable reference to an agent runtime session or process."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_id: str = Field(min_length=1)
    vendor: str = Field(min_length=1)
    mode: OperationMode
    native_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdapterMetering(BaseModel):
    """Usage units reported by an adapter for FinOps attribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_id: str = Field(min_length=1)
    usage_units: dict[str, Decimal] = Field(default_factory=dict)
    cost_refs: tuple[str, ...] = Field(default_factory=tuple)
    measured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("measured_at")
    @classmethod
    def measured_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """Require timezone-aware metering timestamps."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        return value


class LifecycleEvent(BaseModel):
    """Mode-agnostic lifecycle event emitted by every executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    task_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: LifecycleStatus
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operation_mode: OperationMode
    runtime: str = Field(min_length=1)
    trace_id: str | None = Field(default=None, min_length=1)
    cost_refs: tuple[str, ...] = Field(default_factory=tuple)
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """Require timezone-aware lifecycle timestamps."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


"""
Workflow and step data model definitions for the AOP orchestration engine.

This module owns the static (data-only) layer of the orchestration engine:

    * `StepType`        - enum of every supported step kind.
    * `WorkflowStatus`  - lifecycle states of a workflow run.
    * `StepStatus`      - lifecycle states of a single step within a run.
    * `RetryPolicy`     - retry configuration attached to a single step.
    * `StepDefinition`  - declarative description of one step.
    * `WorkflowDefinition` - ordered/DAG description of a whole workflow.
    * `StepResult`      - outcome of executing one step.
    * `WorkflowResult`  - aggregate outcome of executing a whole workflow.
    * `ExecutionContext` - mutable bag passed through every step during a run.

The actual executor lives in :mod:`app.orchestration.orchestration_engine`;
this file deliberately contains *no* I/O or evaluation logic so that the
schema can be imported anywhere (including request/response models in the
FastAPI router) without dragging async-runtime dependencies along.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StepType(str, Enum):
    """Kinds of step an :class:`OrchestrationEngine` knows how to execute."""

    LLM_CALL = "llm_call"
    API_CALL = "api_call"
    TRANSFORM = "transform"
    CONDITION = "condition"
    PARALLEL = "parallel"


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    TIMEOUT = "TIMEOUT"


class StepStatus(str, Enum):
    """Lifecycle status of a single step within a workflow run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"
    FALLBACK = "FALLBACK"


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class RetryPolicy(BaseModel):
    """Per-step retry behaviour.

    Defaults are deliberately conservative: short backoff with exponential
    growth, capped at 30s, with no more than three total attempts. The
    ``retry_on`` list, when non-empty, restricts retries to exceptions whose
    stringified form contains one of the listed substrings (case-sensitive).
    An empty ``retry_on`` retries on every failure.
    """

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1, le=20)
    backoff_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    max_backoff_seconds: float = Field(default=30.0, ge=0.0, le=600.0)
    retry_on: List[str] = Field(default_factory=list)

    def should_retry(self, attempt: int, exc: BaseException) -> bool:
        """Return True if a retry should be attempted for ``exc`` on ``attempt``."""
        # ``attempt`` is 1-indexed: the first try is attempt=1, first retry attempt=2.
        if attempt >= self.max_attempts:
            return False
        if not self.retry_on:
            return True
        msg = str(exc)
        return any(token in msg for token in self.retry_on)

    def backoff_for(self, attempt: int) -> float:
        """Return how long to sleep before the ``attempt``-th try (1-indexed)."""
        if attempt <= 1:
            return 0.0
        delay = self.backoff_seconds * (self.backoff_multiplier ** (attempt - 2))
        return min(delay, self.max_backoff_seconds)


# ---------------------------------------------------------------------------
# Step + workflow definitions
# ---------------------------------------------------------------------------


class StepDefinition(BaseModel):
    """Declarative description of one step in a workflow.

    The ``config`` field is a free-form mapping whose expected keys depend
    on :attr:`type`:

    * ``llm_call`` - ``{"provider": "...", "model": "...", "messages": [...],
      "temperature": float, "max_tokens": int, ...}``
    * ``api_call`` - ``{"url": "...", "method": "GET", "headers": {...},
      "body": ..., "timeout": float}``
    * ``transform`` - ``{"expression": "ctx['x'] * 2"}`` (Python eval; sandboxed)
    * ``condition`` - ``{"expression": "ctx['count'] > 0",
      "branches": {"true": <StepDefinition>, "false": <StepDefinition>}}``
    * ``parallel`` - ``{"steps": [<StepDefinition>, ...]}`` (sub-steps run
      concurrently via ``asyncio.gather``)

    Other common fields:

    * ``depends_on`` - step IDs that must complete before this one runs.
      Empty list means "respect workflow order only".
    * ``retry`` - :class:`RetryPolicy` for failure recovery.
    * ``fallback`` - alternative :class:`StepDefinition` to execute on
      permanent failure (after retries are exhausted).
    * ``output_key`` - key under which the step's ``output`` is written into
      :class:`ExecutionContext`. Defaults to the step ``id``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=200)
    name: Optional[str] = Field(default=None, max_length=200)
    type: StepType
    config: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    retry: Optional[RetryPolicy] = None
    fallback: Optional["StepDefinition"] = None
    output_key: Optional[str] = Field(default=None, max_length=200)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_no_dots(cls, v: str) -> str:
        # Avoid breaking dotted lookups in transform expressions.
        if "." in v or "/" in v:
            raise ValueError("Step id must not contain '.' or '/'.")
        return v

    def resolve_output_key(self) -> str:
        return self.output_key or self.id


# Allow self-referential fallback typing.
StepDefinition.model_rebuild()


class WorkflowDefinition(BaseModel):
    """A workflow is an ordered list of steps plus metadata.

    Steps may declare explicit ``depends_on`` edges that turn the workflow
    into a DAG. The executor respects both the declared ``steps`` order
    (for steps without dependencies) and the dependency graph (for steps
    with explicit edges).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    version: str = Field(default="1.0.0", max_length=50)
    steps: List[StepDefinition] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("steps")
    @classmethod
    def _unique_step_ids(cls, steps: List[StepDefinition]) -> List[StepDefinition]:
        seen: set = set()
        for step in steps:
            if step.id in seen:
                raise ValueError(f"Duplicate step id in workflow: {step.id!r}")
            seen.add(step.id)
        return steps

    def step_map(self) -> Dict[str, StepDefinition]:
        """Return a dict mapping step id -> definition."""
        return {s.id: s for s in self.steps}

    def validate_dependencies(self) -> None:
        """Raise ``ValueError`` if any ``depends_on`` references a missing step."""
        known = {s.id for s in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in known:
                    raise ValueError(
                        f"Step {step.id!r} depends on unknown step {dep!r}."
                    )


# ---------------------------------------------------------------------------
# Runtime result models
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StepResult(BaseModel):
    """Outcome of executing a single step."""

    model_config = ConfigDict(extra="allow")

    step_id: str
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    attempts: int = 0
    duration_ms: Optional[float] = None
    used_fallback: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = StepStatus.RUNNING
        self.started_at = _utcnow()

    def mark_completed(self, output: Any) -> None:
        self.status = StepStatus.COMPLETED
        self.output = output
        self.completed_at = _utcnow()
        self.duration_ms = (
            (self.completed_at - self.started_at).total_seconds() * 1000.0
        )

    def mark_failed(self, exc: BaseException) -> None:
        self.status = StepStatus.FAILED
        self.error = f"{type(exc).__name__}: {exc}"
        self.completed_at = _utcnow()
        self.duration_ms = (
            (self.completed_at - self.started_at).total_seconds() * 1000.0
        )

    def mark_skipped(self, reason: str = "") -> None:
        self.status = StepStatus.SKIPPED
        self.error = reason or None
        self.completed_at = _utcnow()


class WorkflowResult(BaseModel):
    """Aggregate outcome of executing a whole workflow."""

    model_config = ConfigDict(extra="allow")

    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    step_results: Dict[str, StepResult] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    final_context: Optional[Dict[str, Any]] = None

    def mark_completed(self, status: WorkflowStatus = WorkflowStatus.COMPLETED) -> None:
        self.status = status
        self.completed_at = _utcnow()

    def to_summary(self) -> Dict[str, Any]:
        """Return a small dict suitable for API responses / logging."""
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "step_count": len(self.step_results),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Execution context
# ---------------------------------------------------------------------------


class ExecutionContext(BaseModel):
    """Mutable bag passed through every step during a workflow run.

    A context has three layers, exposed to step expressions as a single
    ``ctx`` mapping at evaluation time:

    * ``inputs``  - read-only initial inputs from the caller; preserved verbatim.
    * ``state``   - scratch space that steps may freely read and write.
    * ``outputs`` - per-step named outputs (keyed by each step's
      ``output_key``, which defaults to its ``id``).

    Step expressions can reference them as ``ctx['inputs']['x']``,
    ``ctx['state']['y']``, ``ctx['outputs']['previous_step']``.
    """

    model_config = ConfigDict(extra="forbid")

    inputs: Dict[str, Any] = Field(default_factory=dict)
    state: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def as_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Return the context as the nested mapping exposed to expressions."""
        return {
            "inputs": dict(self.inputs),
            "state": dict(self.state),
            "outputs": dict(self.outputs),
            "metadata": dict(self.metadata),
        }

    def set_output(self, key: str, value: Any) -> None:
        self.outputs[key] = value

    def merge(self, update: Mapping[str, Any]) -> None:
        """Shallow-merge ``update`` into ``state``."""
        for k, v in update.items():
            self.state[k] = v

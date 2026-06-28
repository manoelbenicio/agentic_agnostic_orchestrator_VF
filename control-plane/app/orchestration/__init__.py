"""
Orchestration engine for the AOP control plane.

This package implements a small, dependency-free workflow engine that lets
operators compose multi-step LLM, HTTP, and data-transform jobs from
declarative :class:`WorkflowDefinition` objects.

Public surface
--------------
Data model (``app.orchestration.workflow``)
    * :class:`StepType`         - kinds of step the engine can execute.
    * :class:`WorkflowStatus`   - lifecycle status of a workflow run.
    * :class:`StepStatus`       - lifecycle status of a single step.
    * :class:`RetryPolicy`      - retry/backoff configuration for a step.
    * :class:`StepDefinition`   - declarative description of one step.
    * :class:`WorkflowDefinition` - ordered/DAG description of a workflow.
    * :class:`StepResult`       - outcome of executing one step.
    * :class:`WorkflowResult`   - aggregate outcome of a workflow run.
    * :class:`ExecutionContext` - mutable bag passed through every step.

Executor (``app.orchestration.orchestration_engine``)
    * :class:`OrchestrationEngine` - the executor.
    * :data:`router`                - default :class:`fastapi.APIRouter` mounted
      at ``/orchestration/workflows`` (use ``app.include_router(router)``).
    * :func:`build_orchestration_router` - factory that re-builds the router
      (useful for tests).
    * :func:`get_engine` / :func:`set_engine` - module-level engine singleton
      accessors used by the router endpoints.
"""

from .workflow import (
    ExecutionContext,
    RetryPolicy,
    StepDefinition,
    StepResult,
    StepStatus,
    StepType,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStatus,
)
from .orchestration_engine import (
    AdapterResolver,
    OrchestrationEngine,
    build_orchestration_router,
    get_engine,
    router,
    set_engine,
)

__all__ = [
    # Data model
    "StepType",
    "WorkflowStatus",
    "StepStatus",
    "RetryPolicy",
    "StepDefinition",
    "WorkflowDefinition",
    "StepResult",
    "WorkflowResult",
    "ExecutionContext",
    # Executor
    "AdapterResolver",
    "OrchestrationEngine",
    # FastAPI integration
    "router",
    "build_orchestration_router",
    "get_engine",
    "set_engine",
]

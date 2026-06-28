"""Tech-Lead coordinator that runs as a selectable agent seat."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from core import TaskEnvelope
from scheduler import AdmissionStatus, QuotaAwareScheduler


class Planner(Protocol):
    """Plan decomposition boundary, backed by HerdMaster ProjectPlanner when wired."""

    async def decompose(self, objective: str, workers: Sequence[str]) -> list[dict[str, Any]]:
        """Return task specs for the selected workers."""
        ...


DispatchCallable = Callable[[TaskEnvelope], Awaitable[Any]]


class ApprovalRequired(RuntimeError):
    """Raised when autonomy requires human approval before spend/spawn."""


@dataclass(frozen=True, slots=True)
class TechLeadConfig:
    """Configuration for a selectable Tech-Lead seat."""

    tenant_id: str
    project_id: str
    tech_lead_agent_id: str
    tech_lead_seat_id: str
    vendor: str
    autonomy_level: int = 2
    max_fanout: int = 3

    def __post_init__(self) -> None:
        """Validate autonomy and fan-out bounds."""
        if not 0 <= self.autonomy_level <= 4:
            raise ValueError("autonomy_level must be 0..4")
        if self.max_fanout < 1:
            raise ValueError("max_fanout must be >= 1")


@dataclass(frozen=True, slots=True)
class PlanTask:
    """One decomposed worker task."""

    task_id: str
    worker_id: str
    prompt: str
    estimated_burn_seconds: int = 0
    operation_mode: str = "socket"


@dataclass(frozen=True, slots=True)
class Plan:
    """Tech-Lead plan plus dispatch/queue accounting."""

    objective: str
    tech_lead_agent_id: str
    tech_lead_seat_id: str
    tasks: tuple[PlanTask, ...]
    queued: tuple[PlanTask, ...] = ()
    dispatched: tuple[PlanTask, ...] = ()
    approval_required: bool = False
    eta: dict[str, Any] = field(default_factory=dict)


class SimplePlanner:
    """Fallback planner that assigns one prompt per permitted worker."""

    async def decompose(self, objective: str, workers: Sequence[str]) -> list[dict[str, Any]]:
        """Return a small deterministic plan for tests/local bootstrap."""
        return [
            {
                "task_id": f"{worker}-task",
                "worker_id": worker,
                "prompt": f"{objective}\n\nWorker: {worker}",
                "estimated_burn_seconds": 300,
            }
            for worker in workers
        ]


class TechLeadCoordinator:
    """Coordinate goal decomposition and bounded worker dispatch as a seat."""

    def __init__(
        self,
        config: TechLeadConfig,
        *,
        seat_pool: Any,
        scheduler: QuotaAwareScheduler,
        dispatch: DispatchCallable,
        planner: Planner | None = None,
        eta_estimator: Any | None = None,
    ) -> None:
        """Create a Tech-Lead coordinator with injectable planner and scheduler."""
        self.config = config
        self.seat_pool = seat_pool
        self.scheduler = scheduler
        self.dispatch = dispatch
        self.planner = planner or SimplePlanner()
        self.eta_estimator = eta_estimator

    async def plan(
        self,
        objective: str,
        *,
        permitted_workers: Sequence[str],
    ) -> Plan:
        """Decompose an objective into a bounded fan-out plan."""
        workers = tuple(permitted_workers[: self.config.max_fanout])
        raw_tasks = await self.planner.decompose(objective, workers)
        tasks = tuple(self._plan_task(index, item, workers) for index, item in enumerate(raw_tasks))
        eta = self._estimate_eta(tasks, workers)
        return Plan(
            objective=objective,
            tech_lead_agent_id=self.config.tech_lead_agent_id,
            tech_lead_seat_id=self.config.tech_lead_seat_id,
            tasks=tasks,
            approval_required=self.requires_approval(),
            eta=eta,
        )

    async def execute(
        self,
        objective: str,
        *,
        permitted_workers: Sequence[str],
        parent_seat: Any,
        approved: bool = False,
    ) -> Plan:
        """Plan and dispatch workers, queueing when scheduler admission denies."""
        plan = await self.plan(objective, permitted_workers=permitted_workers)
        if plan.approval_required and not approved:
            raise ApprovalRequired("human approval required before spend or spawn")

        dispatched: list[PlanTask] = []
        queued: list[PlanTask] = []
        for plan_task in plan.tasks:
            subagent_seat = self.seat_pool.acquire_subagent(parent_seat)
            task = self._envelope(plan_task, subagent_seat)
            decision = self.scheduler.admit(
                task,
                vendor=self.config.vendor,
                estimated_burn_seconds=plan_task.estimated_burn_seconds,
            )
            if decision.status is AdmissionStatus.DISPATCH:
                await self.dispatch(task)
                dispatched.append(plan_task)
            else:
                queued.append(plan_task)

        return Plan(
            objective=plan.objective,
            tech_lead_agent_id=plan.tech_lead_agent_id,
            tech_lead_seat_id=plan.tech_lead_seat_id,
            tasks=plan.tasks,
            queued=tuple(queued),
            dispatched=tuple(dispatched),
            approval_required=False,
            eta=plan.eta,
        )

    def requires_approval(self) -> bool:
        """Return True when autonomy requires approval before spend/spawn."""
        return self.config.autonomy_level <= 1

    def _plan_task(self, index: int, item: dict[str, Any], workers: Sequence[str]) -> PlanTask:
        worker = str(item.get("worker_id") or item.get("assigned_to") or item.get("agent") or workers[index % len(workers)])
        return PlanTask(
            task_id=str(item.get("task_id") or item.get("id") or f"{worker}-task-{index + 1}"),
            worker_id=worker,
            prompt=str(item.get("prompt") or item.get("description") or item.get("title") or ""),
            estimated_burn_seconds=int(item.get("estimated_burn_seconds") or item.get("seat_seconds") or 0),
            operation_mode=str(item.get("operation_mode") or "socket"),
        )

    def _envelope(self, plan_task: PlanTask, seat: Any) -> TaskEnvelope:
        return TaskEnvelope(
            task_id=plan_task.task_id,
            tenant_id=self.config.tenant_id,
            project_id=self.config.project_id,
            assignee_runtime=plan_task.worker_id,
            prompt=plan_task.prompt,
            budget={"seat_seconds": plan_task.estimated_burn_seconds},
            credential_ref=f"seat://{getattr(seat, 'seat_id', self.config.tech_lead_seat_id)}",
            operation_mode=plan_task.operation_mode,
        )

    def _estimate_eta(self, tasks: Sequence[PlanTask], workers: Sequence[str]) -> dict[str, Any]:
        if self.eta_estimator is None:
            return {"task_count": len(tasks), "parallelism_factor": max(1, len(workers))}
        estimate = self.eta_estimator.estimate(
            [{"id": task.task_id, "assigned_to": task.worker_id} for task in tasks],
            [{"agent": worker} for worker in workers],
            [{"id": worker, "avg_task_seconds": 1800} for worker in workers],
            "M",
        )
        return {
            "expected_hours": getattr(estimate, "expected_hours", None),
            "rationale": getattr(estimate, "rationale", ""),
        }


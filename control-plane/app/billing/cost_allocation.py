"""
Cost allocation and budget enforcement for the AOP control plane billing module.

This module owns the *per-tenant* view of cost: who spent what, when, and
against which budget. It complements the lower-level :mod:`finops` module
(which records raw token / seat usage) by adding:

    * explicit tenant-scoped cost allocations tagged by category
      (e.g. ``"llm_tokens"``, ``"seats"``, ``"compute"``);
    * monthly budget limits with configurable warning thresholds;
    * daily time-series breakdowns;
    * a FastAPI router mounted at ``/billing`` that exposes the operations
      over HTTP.

Storage
-------
Allocations and budgets live in process memory (thread-safe) by default.
That keeps the module self-contained and unit-testable. The service
intentionally exposes a small, repository-shaped surface so a Postgres-
backed implementation can drop in later without changing call sites.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, DefaultDict, Dict, List, Mapping, Optional, Sequence

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("billing.cost_allocation")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")

DEFAULT_WARNING_THRESHOLD_PCT = Decimal("80")

#: Cost categories the service understands out of the box. Callers may pass
#: any string; this list is only used for documentation and validation hints.
KNOWN_CATEGORIES = frozenset({
    "llm_tokens",
    "llm_image",
    "seats",
    "compute",
    "storage",
    "network",
    "general",
})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return _utcnow().date()


def _month_bounds(at: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Return the ``[start, end)`` UTC interval covering the month of ``at``."""
    moment = at or _utcnow()
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start, next_month


# ---------------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostAllocation:
    """A single tenant-scoped cost entry."""

    cost_id: str
    tenant_id: str
    amount_usd: Decimal
    category: str
    description: str
    allocated_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BudgetLimit:
    """Monthly budget cap with an alerting threshold.

    ``period_start`` / ``period_end`` describe the *current* budget window
    (default: calendar month UTC). ``monthly_limit_usd`` is the hard cap;
    ``warning_threshold_pct`` is the percentage at which ``check_budget_exceeded``
    raises the ``warning`` flag without flipping ``exceeded``.
    """

    tenant_id: str
    monthly_limit_usd: Decimal
    period_start: datetime
    period_end: datetime
    warning_threshold_pct: Decimal = DEFAULT_WARNING_THRESHOLD_PCT
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class TenantCostSummary:
    """Aggregated cost view for one tenant over a time window."""

    tenant_id: str
    total_cost_usd: Decimal
    period_start: datetime
    period_end: datetime
    allocation_count: int
    by_category: Mapping[str, Decimal]


@dataclass(frozen=True, slots=True)
class DailyCost:
    """Per-day cost bucket used by :meth:`CostAllocationService.get_daily_breakdown`."""

    date: date
    cost_usd: Decimal
    allocation_count: int


@dataclass(frozen=True)
class BudgetCheckResult:
    """Outcome of a budget check for one tenant."""

    tenant_id: str
    budget_limit_usd: Decimal
    current_spend_usd: Decimal
    remaining_usd: Decimal
    utilization_pct: Decimal
    exceeded: bool
    warning: bool
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------------------
# FastAPI request / response models
# ---------------------------------------------------------------------------


class AllocateCostRequest(BaseModel):
    """Request body for ``POST /billing/allocations``."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1, max_length=200)
    amount_usd: Decimal = Field(..., ge=ZERO, le=Decimal("1000000000"))
    category: str = Field(default="general", min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SetBudgetRequest(BaseModel):
    """Request body for ``PUT /billing/budgets/{tenant_id}``."""

    model_config = ConfigDict(extra="forbid")

    monthly_limit_usd: Decimal = Field(..., ge=ZERO, le=Decimal("1000000000000"))
    warning_threshold_pct: Decimal = Field(
        default=DEFAULT_WARNING_THRESHOLD_PCT, ge=ZERO, le=ONE_HUNDRED,
    )


class CategoryCost(BaseModel):
    category: str
    cost_usd: Decimal


class TenantCostResponse(BaseModel):
    """Response body for tenant cost queries."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    total_cost_usd: Decimal
    period_start: datetime
    period_end: datetime
    allocation_count: int
    by_category: List[CategoryCost]


class DailyCostEntry(BaseModel):
    date: date
    cost_usd: Decimal
    allocation_count: int


class DailyBreakdownResponse(BaseModel):
    tenant_id: str
    period_start: datetime
    period_end: datetime
    daily: List[DailyCostEntry]


class BudgetResponse(BaseModel):
    tenant_id: str
    monthly_limit_usd: Decimal
    period_start: datetime
    period_end: datetime
    warning_threshold_pct: Decimal
    updated_at: datetime


class BudgetCheckResponse(BaseModel):
    tenant_id: str
    budget_limit_usd: Decimal
    current_spend_usd: Decimal
    remaining_usd: Decimal
    utilization_pct: Decimal
    exceeded: bool
    warning: bool
    period_start: datetime
    period_end: datetime


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CostAllocationService:
    """Tenant-scoped cost allocation + budget enforcement.

    The service is thread-safe; all internal mutation happens under a single
    re-entrant lock. Storage is in-memory; swap in a repository for Postgres
    persistence when ready.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._allocations: DefaultDict[str, List[CostAllocation]] = defaultdict(list)
        self._budgets: Dict[str, BudgetLimit] = {}

    # ------------------------------------------------------------ allocations

    def allocate_cost(
        self,
        tenant_id: str,
        amount_usd: Decimal | float | int | str,
        *,
        category: str = "general",
        description: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
        allocated_at: Optional[datetime] = None,
    ) -> CostAllocation:
        """Record a single cost allocation against ``tenant_id``.

        Parameters
        ----------
        tenant_id:
            Tenant receiving the charge.
        amount_usd:
            Cost amount. Must be non-negative. Accepted as ``Decimal``,
            ``int``, ``float``, or numeric string (floats are coerced via
            ``str`` to avoid binary-float rounding artefacts).
        category:
            Cost category. Free-form; known values are listed in
            :data:`KNOWN_CATEGORIES` for documentation only.
        description:
            Human-readable description.
        metadata:
            Arbitrary structured metadata persisted alongside the allocation.
        allocated_at:
            Override the allocation timestamp (UTC). Defaults to "now".

        Raises
        ------
        ValueError
            If ``amount_usd`` is negative or ``tenant_id`` is empty.
        """
        if not tenant_id:
            raise ValueError("tenant_id must be a non-empty string")

        amount = _coerce_decimal(amount_usd)
        if amount < ZERO:
            raise ValueError(f"amount_usd must be >= 0, got {amount}")

        allocation = CostAllocation(
            cost_id=f"cost-{uuid.uuid4()}",
            tenant_id=tenant_id,
            amount_usd=amount,
            category=str(category),
            description=str(description),
            allocated_at=allocated_at or _utcnow(),
            metadata=dict(metadata or {}),
        )

        with self._lock:
            self._allocations[tenant_id].append(allocation)

        logger.info(
            "allocated cost_id=%s tenant=%s amount=%s category=%s",
            allocation.cost_id, tenant_id, amount, category,
        )

        # Soft check: warn (don't fail) when budget is breached.
        try:
            check = self.check_budget_exceeded(tenant_id)
        except ValueError:
            # No budget configured; nothing to check.
            return allocation
        if check.exceeded:
            logger.warning(
                "tenant %s over budget: %s / %s (utilization=%s%%)",
                tenant_id, check.current_spend_usd, check.budget_limit_usd,
                check.utilization_pct,
            )
        elif check.warning:
            logger.info(
                "tenant %s approaching budget: %s%% of %s",
                tenant_id, check.utilization_pct, check.budget_limit_usd,
            )
        return allocation

    def get_tenant_costs(
        self,
        tenant_id: str,
        *,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> TenantCostSummary:
        """Return the total cost for ``tenant_id`` in ``[period_start, period_end)``.

        When neither bound is supplied, the current calendar month is used.
        """
        start, end = self._resolve_window(period_start, period_end)
        with self._lock:
            allocations = self._allocations.get(tenant_id, [])

        relevant = [a for a in allocations if start <= a.allocated_at < end]
        total = ZERO
        by_category: Dict[str, Decimal] = defaultdict(lambda: ZERO)
        for a in relevant:
            total += a.amount_usd
            by_category[a.category] += a.amount_usd

        return TenantCostSummary(
            tenant_id=tenant_id,
            total_cost_usd=total,
            period_start=start,
            period_end=end,
            allocation_count=len(relevant),
            by_category=dict(by_category),
        )

    def get_daily_breakdown(
        self,
        tenant_id: str,
        *,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> List[DailyCost]:
        """Return one :class:`DailyCost` per calendar day in the window.

        Days with zero spend are included so callers can render a contiguous
        timeline. Days are bucketed by the allocation's UTC date.
        """
        start, end = self._resolve_window(period_start, period_end)
        with self._lock:
            allocations = self._allocations.get(tenant_id, [])

        per_day: Dict[date, List[Decimal]] = defaultdict(list)
        for a in allocations:
            if start <= a.allocated_at < end:
                per_day[a.allocated_at.date()].append(a.amount_usd)

        # Emit every UTC day in [start.date(), end.date()) inclusive of start
        # but exclusive of end (matches the half-open window semantics).
        result: List[DailyCost] = []
        cursor = start.date()
        last = end.date()
        while cursor < last:
            amounts = per_day.get(cursor, [])
            result.append(
                DailyCost(
                    date=cursor,
                    cost_usd=sum(amounts, ZERO),
                    allocation_count=len(amounts),
                )
            )
            cursor = cursor + timedelta(days=1)
        return result

    # ---------------------------------------------------------------- budgets

    def set_budget_limit(
        self,
        tenant_id: str,
        monthly_limit_usd: Decimal | float | int | str,
        *,
        warning_threshold_pct: Decimal | float | int | str = DEFAULT_WARNING_THRESHOLD_PCT,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> BudgetLimit:
        """Create or replace the monthly budget for ``tenant_id``."""
        if not tenant_id:
            raise ValueError("tenant_id must be a non-empty string")

        limit = _coerce_decimal(monthly_limit_usd)
        if limit < ZERO:
            raise ValueError(f"monthly_limit_usd must be >= 0, got {limit}")

        threshold = _coerce_decimal(warning_threshold_pct)
        if threshold < ZERO or threshold > ONE_HUNDRED:
            raise ValueError(
                f"warning_threshold_pct must be in [0, 100], got {threshold}"
            )

        start, end = (period_start, period_end) if period_start and period_end else _month_bounds()

        budget = BudgetLimit(
            tenant_id=tenant_id,
            monthly_limit_usd=limit,
            period_start=start,
            period_end=end,
            warning_threshold_pct=threshold,
            updated_at=_utcnow(),
        )
        with self._lock:
            self._budgets[tenant_id] = budget

        logger.info(
            "set budget tenant=%s limit=%s window=%s..%s",
            tenant_id, limit, start.isoformat(), end.isoformat(),
        )
        return budget

    def get_budget_limit(self, tenant_id: str) -> Optional[BudgetLimit]:
        """Return the configured budget for ``tenant_id``, or ``None`` if unset."""
        with self._lock:
            return self._budgets.get(tenant_id)

    def check_budget_exceeded(self, tenant_id: str) -> BudgetCheckResult:
        """Return the current budget status for ``tenant_id``.

        Raises
        ------
        ValueError
            If no budget has been configured for ``tenant_id``.
        """
        with self._lock:
            budget = self._budgets.get(tenant_id)
        if budget is None:
            raise ValueError(f"No budget configured for tenant {tenant_id!r}")

        summary = self.get_tenant_costs(
            tenant_id,
            period_start=budget.period_start,
            period_end=budget.period_end,
        )
        spend = summary.total_cost_usd
        limit = budget.monthly_limit_usd

        if limit > ZERO:
            utilization = (spend / limit) * ONE_HUNDRED
            remaining = max(ZERO, limit - spend)
        else:
            # Zero-limit budget: any spend counts as 100% (or infinity) utilization.
            utilization = ONE_HUNDRED if spend > ZERO else ZERO
            remaining = ZERO

        return BudgetCheckResult(
            tenant_id=tenant_id,
            budget_limit_usd=limit,
            current_spend_usd=spend,
            remaining_usd=remaining,
            utilization_pct=utilization.quantize(Decimal("0.01")),
            exceeded=spend > limit,
            warning=spend >= (limit * budget.warning_threshold_pct / ONE_HUNDRED)
                    and not (spend > limit),
            period_start=budget.period_start,
            period_end=budget.period_end,
        )

    # ------------------------------------------------------------- internals

    def _resolve_window(
        self,
        period_start: Optional[datetime],
        period_end: Optional[datetime],
    ) -> tuple[datetime, datetime]:
        if period_start is None and period_end is None:
            return _month_bounds()
        if period_start is None or period_end is None:
            raise ValueError("period_start and period_end must be provided together")
        if period_end <= period_start:
            raise ValueError("period_end must be strictly after period_start")
        return period_start, period_end

    # Useful for tests / migrations.
    def allocations_for(self, tenant_id: str) -> Sequence[CostAllocation]:
        with self._lock:
            return tuple(self._allocations.get(tenant_id, ()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_decimal(value: Any) -> Decimal:
    """Coerce a numeric value to ``Decimal`` without binary-float artefacts."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int,)):
        return Decimal(value)
    if isinstance(value, float):
        # Round-trip through ``str`` to avoid 0.1 + 0.2 != 0.3 style surprises.
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Cannot coerce {type(value).__name__} to Decimal")


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------


def build_billing_router(service: Optional[CostAllocationService] = None) -> APIRouter:
    """Build the FastAPI router mounted at ``/billing``."""
    svc = service  # captured by the closures below

    def _get_service() -> CostAllocationService:
        return svc if svc is not None else _default_service

    router = APIRouter(prefix="/billing", tags=["billing"])

    @router.post(
        "/allocations",
        response_model=TenantCostResponse,
        status_code=201,
        summary="Record a cost allocation for a tenant",
    )
    async def create_allocation(req: AllocateCostRequest) -> TenantCostResponse:
        service = _get_service()
        try:
            service.allocate_cost(
                tenant_id=req.tenant_id,
                amount_usd=req.amount_usd,
                category=req.category,
                description=req.description,
                metadata=req.metadata,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_allocation", "reason": str(e)},
            ) from e
        return _summary_response(service.get_tenant_costs(req.tenant_id))

    @router.get(
        "/tenants/{tenant_id}/costs",
        response_model=TenantCostResponse,
        summary="Get total cost for a tenant over an optional time window",
    )
    async def get_tenant_costs(
        tenant_id: str,
        period_start: Optional[datetime] = Query(default=None),
        period_end: Optional[datetime] = Query(default=None),
    ) -> TenantCostResponse:
        service = _get_service()
        try:
            summary = service.get_tenant_costs(
                tenant_id, period_start=period_start, period_end=period_end,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_window", "reason": str(e)},
            ) from e
        return _summary_response(summary)

    @router.get(
        "/tenants/{tenant_id}/costs/daily",
        response_model=DailyBreakdownResponse,
        summary="Per-day cost breakdown for a tenant",
    )
    async def get_daily_breakdown(
        tenant_id: str,
        period_start: Optional[datetime] = Query(default=None),
        period_end: Optional[datetime] = Query(default=None),
    ) -> DailyBreakdownResponse:
        service = _get_service()
        try:
            start, end = service._resolve_window(period_start, period_end)
            daily = service.get_daily_breakdown(
                tenant_id, period_start=period_start, period_end=period_end,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_window", "reason": str(e)},
            ) from e
        return DailyBreakdownResponse(
            tenant_id=tenant_id,
            period_start=start,
            period_end=end,
            daily=[DailyCostEntry(**vars_as_dict(d)) for d in daily],
        )

    @router.put(
        "/budgets/{tenant_id}",
        response_model=BudgetResponse,
        summary="Set (or replace) the monthly budget for a tenant",
    )
    async def set_budget(tenant_id: str, req: SetBudgetRequest) -> BudgetResponse:
        service = _get_service()
        try:
            budget = service.set_budget_limit(
                tenant_id,
                req.monthly_limit_usd,
                warning_threshold_pct=req.warning_threshold_pct,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_budget", "reason": str(e)},
            ) from e
        return _budget_response(budget)

    @router.get(
        "/budgets/{tenant_id}",
        response_model=BudgetResponse,
        summary="Get the current budget configuration for a tenant",
    )
    async def get_budget(tenant_id: str) -> BudgetResponse:
        service = _get_service()
        budget = service.get_budget_limit(tenant_id)
        if budget is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "budget_not_found", "tenant_id": tenant_id},
            )
        return _budget_response(budget)

    @router.get(
        "/budgets/{tenant_id}/check",
        response_model=BudgetCheckResponse,
        summary="Check whether a tenant is over (or near) budget",
    )
    async def check_budget(tenant_id: str) -> BudgetCheckResponse:
        service = _get_service()
        try:
            result = service.check_budget_exceeded(tenant_id)
        except ValueError as e:
            raise HTTPException(
                status_code=404,
                detail={"code": "budget_not_found", "reason": str(e)},
            ) from e
        return BudgetCheckResponse(**vars_as_dict(result))

    @router.get(
        "/health",
        summary="Liveness probe for the billing module",
    )
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "module": "billing"}

    return router


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _summary_response(summary: TenantCostSummary) -> TenantCostResponse:
    return TenantCostResponse(
        tenant_id=summary.tenant_id,
        total_cost_usd=summary.total_cost_usd,
        period_start=summary.period_start,
        period_end=summary.period_end,
        allocation_count=summary.allocation_count,
        by_category=[
            CategoryCost(category=cat, cost_usd=amt)
            for cat, amt in sorted(summary.by_category.items())
        ],
    )


def _budget_response(budget: BudgetLimit) -> BudgetResponse:
    return BudgetResponse(
        tenant_id=budget.tenant_id,
        monthly_limit_usd=budget.monthly_limit_usd,
        period_start=budget.period_start,
        period_end=budget.period_end,
        warning_threshold_pct=budget.warning_threshold_pct,
        updated_at=budget.updated_at,
    )


def vars_as_dict(obj: Any) -> Dict[str, Any]:
    """``dataclasses.asdict``-style dump without copying nested mappings."""
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return dict(vars(obj))


# ---------------------------------------------------------------------------
# Module-level singleton + default router
# ---------------------------------------------------------------------------


_default_service = CostAllocationService()


def get_service() -> CostAllocationService:
    """Return the process-wide :class:`CostAllocationService`."""
    return _default_service


def set_service(service: CostAllocationService) -> None:
    """Replace the process-wide service (primarily for tests)."""
    global _default_service
    _default_service = service


#: Default router instance for `app.include_router(...)` callers.
router = build_billing_router(_default_service)

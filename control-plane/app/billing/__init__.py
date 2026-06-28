"""
Billing module for the AOP control plane.

This package provides tenant-scoped cost allocation and budget enforcement
on top of the lower-level :mod:`finops` cost engine.

Public surface
--------------
Service (:mod:`app.billing.cost_allocation`)
    * :class:`CostAllocationService` - the executor. Provides
      ``allocate_cost``, ``get_tenant_costs``, ``get_daily_breakdown``,
      ``set_budget_limit``, ``check_budget_exceeded``, plus
      ``get_budget_limit`` and ``allocations_for`` accessors.
    * :data:`router` - default :class:`fastapi.APIRouter` mounted at
      ``/billing`` (use ``app.include_router(router)``).
    * :func:`build_billing_router` - factory for building the router
      with a custom service instance (useful for tests).
    * :func:`get_service` / :func:`set_service` - module-level service
      singleton accessors used by the default router endpoints.

Domain models
    * :class:`CostAllocation`  - one tenant-scoped cost entry.
    * :class:`BudgetLimit`     - monthly budget with warning threshold.
    * :class:`TenantCostSummary` - aggregated tenant cost over a window.
    * :class:`DailyCost`       - per-day cost bucket.
    * :class:`BudgetCheckResult` - outcome of a budget check.
"""

from .cost_allocation import (
    BudgetCheckResult,
    BudgetLimit,
    CostAllocation,
    CostAllocationService,
    DailyCost,
    TenantCostSummary,
    build_billing_router,
    get_service,
    router,
    set_service,
)

__all__ = [
    # Domain models
    "CostAllocation",
    "BudgetLimit",
    "TenantCostSummary",
    "DailyCost",
    "BudgetCheckResult",
    # Service + FastAPI integration
    "CostAllocationService",
    "router",
    "build_billing_router",
    "get_service",
    "set_service",
]

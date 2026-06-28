"""FastAPI routes for typed dashboard snapshots."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .aggregation_models import (
    AggregatedDashboard,
    CouplingHealthPanel,
    FinOpsPanel,
    RegistryPanel,
    SchedulerHealthPanel,
    SeatsSessionsPanel,
    TopologyPanel,
    TracingPanel,
)
from .aggregation_service import (
    build_aggregated_dashboard,
    build_coupling_health_panel,
    build_finops_panel,
    build_registry_panel,
    build_scheduler_health_panel,
    build_seats_sessions_panel,
    build_topology_panel,
    build_tracing_panel,
)
from .models import AgentDashboardDetail, AgentDashboardsSnapshot, DashboardsSnapshot, RouteDashboardsSnapshot
from .service import (
    AgentDashboardNotFoundError,
    DashboardScopeSourceUnavailableError,
    DashboardScopeViolationError,
    build_agent_dashboard_detail,
    build_agent_dashboards_snapshot,
    build_dashboards_snapshot,
    build_route_dashboards_snapshot,
)


def build_dashboards_router(
    get_state: Callable[[], Any],
    *,
    routes: Callable[[], list[Any]] | None = None,
    prefix: str = "/api/dashboards",
) -> APIRouter:
    """Build dashboards API routes using the app state dependency."""
    router = APIRouter(prefix=prefix, tags=["dashboards"])

    def current_routes() -> list[Any]:
        return routes() if routes is not None else []

    @router.get("", response_model=DashboardsSnapshot)
    def get_dashboards(state: Any = Depends(get_state)) -> DashboardsSnapshot:
        return build_dashboards_snapshot(state, routes=current_routes())

    @router.get("/agents", response_model=AgentDashboardsSnapshot)
    def get_agent_dashboards(state: Any = Depends(get_state)) -> AgentDashboardsSnapshot:
        return build_agent_dashboards_snapshot(state)

    @router.get("/agents/{agent_id}", response_model=AgentDashboardDetail)
    def get_agent_dashboard(
        agent_id: str,
        tenant_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        state: Any = Depends(get_state),
    ) -> AgentDashboardDetail:
        try:
            return build_agent_dashboard_detail(
                state,
                agent_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except AgentDashboardNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "dashboard_not_found", "reason": str(exc)},
            ) from exc
        except DashboardScopeViolationError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "scope_violation", "reason": str(exc)},
            ) from exc
        except DashboardScopeSourceUnavailableError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "scope_source_unavailable", "reason": str(exc)},
            ) from exc

    @router.get("/agent-summaries", response_model=AgentDashboardsSnapshot)
    def get_agent_summaries(state: Any = Depends(get_state)) -> AgentDashboardsSnapshot:
        return build_agent_dashboards_snapshot(state)

    @router.get("/routes", response_model=RouteDashboardsSnapshot)
    def get_route_dashboards(
        squad: str | None = Query(default=None),
        source_agent: str | None = Query(default=None),
        target_agent: str | None = Query(default=None),
        status: str | None = Query(default=None),
        tenant_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        state: Any = Depends(get_state),
    ) -> RouteDashboardsSnapshot:
        try:
            return build_route_dashboards_snapshot(
                current_routes(),
                state=state,
                squad=squad,
                source_agent=source_agent,
                target_agent=target_agent,
                status=status,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except AgentDashboardNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "dashboard_not_found", "reason": str(exc)},
            ) from exc
        except DashboardScopeViolationError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": "scope_violation", "reason": str(exc)},
            ) from exc
        except DashboardScopeSourceUnavailableError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "scope_source_unavailable", "reason": str(exc)},
            ) from exc

    @router.get("/route-summaries", response_model=RouteDashboardsSnapshot)
    def get_route_summaries(
        squad: str | None = Query(default=None),
        source_agent: str | None = Query(default=None),
        target_agent: str | None = Query(default=None),
        status: str | None = Query(default=None),
        tenant_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        state: Any = Depends(get_state),
    ) -> RouteDashboardsSnapshot:
        return get_route_dashboards(
            squad=squad,
            source_agent=source_agent,
            target_agent=target_agent,
            status=status,
            tenant_id=tenant_id,
            project_id=project_id,
            state=state,
        )

    # -------------------------------------------------------------------
    # Aggregation endpoints
    # -------------------------------------------------------------------

    @router.get("/aggregated", response_model=AggregatedDashboard)
    def get_aggregated_dashboard(
        state: Any = Depends(get_state),
    ) -> AggregatedDashboard:
        """Full aggregated dashboard composing all domain panels."""
        return build_aggregated_dashboard(state)

    @router.get("/aggregated/registry", response_model=RegistryPanel)
    def get_registry_panel(state: Any = Depends(get_state)) -> RegistryPanel:
        return build_registry_panel(state)

    @router.get("/aggregated/seats-sessions", response_model=SeatsSessionsPanel)
    def get_seats_sessions_panel(
        state: Any = Depends(get_state),
    ) -> SeatsSessionsPanel:
        return build_seats_sessions_panel(state)

    @router.get("/aggregated/topology", response_model=TopologyPanel)
    def get_topology_panel(state: Any = Depends(get_state)) -> TopologyPanel:
        return build_topology_panel(state)

    @router.get("/aggregated/tracing", response_model=TracingPanel)
    def get_tracing_panel(state: Any = Depends(get_state)) -> TracingPanel:
        return build_tracing_panel(state)

    @router.get("/aggregated/finops", response_model=FinOpsPanel)
    def get_finops_panel(state: Any = Depends(get_state)) -> FinOpsPanel:
        return build_finops_panel(state)

    @router.get("/aggregated/scheduler-health", response_model=SchedulerHealthPanel)
    def get_scheduler_health_panel(
        state: Any = Depends(get_state),
    ) -> SchedulerHealthPanel:
        return build_scheduler_health_panel(state)

    @router.get("/aggregated/coupling-health", response_model=CouplingHealthPanel)
    def get_coupling_health_panel(
        state: Any = Depends(get_state),
    ) -> CouplingHealthPanel:
        return build_coupling_health_panel(state)

    return router

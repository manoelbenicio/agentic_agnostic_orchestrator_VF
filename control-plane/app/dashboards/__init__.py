"""Dashboard snapshot models and routes for the control-plane app."""

from .aggregation_models import (
    AggregatedDashboard,
    CouplingHealthPanel,
    FinOpsIdleSeatSummary,
    FinOpsPanel,
    FinOpsProjectSummary,
    QuotaVendorSnapshot,
    RegistryAgentSummary,
    RegistryPanel,
    SchedulerHealthPanel,
    SeatSummary,
    SeatsSessionsPanel,
    SessionSummary,
    TopologyEdgeSummary,
    TopologyNodeSummary,
    TopologyPanel,
    TopologySquadSnapshot,
    TracingAgentBurn,
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
from .models import (
    AgentDashboardDetail,
    AgentDashboardSummary,
    AgentDashboardsSnapshot,
    DashboardHealth,
    DashboardsSnapshot,
    RouteDashboard,
    RouteDashboardsSnapshot,
    RouteSummary,
)
from .router import build_dashboards_router
from .service import build_agent_dashboard_detail

__all__ = [
    # Original models
    "AgentDashboardDetail",
    "AgentDashboardSummary",
    "AgentDashboardsSnapshot",
    "DashboardHealth",
    "DashboardsSnapshot",
    "RouteDashboard",
    "RouteDashboardsSnapshot",
    "RouteSummary",
    # Aggregation models
    "AggregatedDashboard",
    "CouplingHealthPanel",
    "FinOpsIdleSeatSummary",
    "FinOpsPanel",
    "FinOpsProjectSummary",
    "QuotaVendorSnapshot",
    "RegistryAgentSummary",
    "RegistryPanel",
    "SchedulerHealthPanel",
    "SeatSummary",
    "SeatsSessionsPanel",
    "SessionSummary",
    "TopologyEdgeSummary",
    "TopologyNodeSummary",
    "TopologyPanel",
    "TopologySquadSnapshot",
    "TracingAgentBurn",
    "TracingPanel",
    # Aggregation service
    "build_aggregated_dashboard",
    "build_coupling_health_panel",
    "build_finops_panel",
    "build_registry_panel",
    "build_scheduler_health_panel",
    "build_seats_sessions_panel",
    "build_topology_panel",
    "build_tracing_panel",
    "build_agent_dashboard_detail",
    # Router
    "build_dashboards_router",
]

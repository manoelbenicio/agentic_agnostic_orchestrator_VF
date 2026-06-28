"""Typed dashboard snapshots for agents and API routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DashboardHealth = Literal["ok", "degraded", "unavailable"]


class AgentDashboardSummary(BaseModel):
    """One agent row for dashboard cards and tables."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    tenant_id: str
    label: str
    vendor: str
    role: str
    status: str
    workspace_id: str | None = None
    pane_id: str | None = None
    active: bool = False
    task_count: int = 0
    active_task_count: int = 0
    done_task_count: int = 0
    blocked_task_count: int = 0
    token_burn: int = 0
    seat_seconds: int = 0
    trace_event_count: int = 0
    total_cost_usd: Decimal = Decimal("0")
    token_cost_usd: Decimal = Decimal("0")
    seat_cost_usd: Decimal = Decimal("0")
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDashboardsSnapshot(BaseModel):
    """Snapshot backing the agent dashboards route."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    health: DashboardHealth = "ok"
    total_agents: int = 0
    active_agents: int = 0
    total_tasks: int = 0
    active_tasks: int = 0
    total_token_burn: int = 0
    total_seat_seconds: int = 0
    total_cost_usd: Decimal = Decimal("0")
    agents: list[AgentDashboardSummary] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


class AgentDashboardDetail(BaseModel):
    """Scoped detail snapshot for one agent dashboard."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    health: DashboardHealth = "ok"
    tenant_id: str
    project_id: str | None = None
    agent: AgentDashboardSummary
    source_issues: list[str] = Field(default_factory=list)


class RouteSummary(BaseModel):
    """One API route summary for route dashboards."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    path: str
    methods: list[str] = Field(default_factory=list)
    name: str | None = None
    tags: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
    project_id: str | None = None
    squad_id: str | None = None
    source_agent: str | None = None
    target_agent: str | None = None
    status: DashboardHealth = "ok"
    request_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    p95_latency_ms: float | None = None
    last_seen_at: datetime | None = None


class RouteDashboard(BaseModel):
    """Grouped dashboard for a route family."""

    model_config = ConfigDict(extra="forbid")

    dashboard_id: str
    title: str
    route_count: int = 0
    request_count: int = 0
    error_count: int = 0
    error_rate: float = 0.0
    p95_latency_ms: float | None = None
    routes: list[RouteSummary] = Field(default_factory=list)


class RouteDashboardsSnapshot(BaseModel):
    """Snapshot backing the route dashboards endpoint."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    health: DashboardHealth = "ok"
    total_routes: int = 0
    total_requests: int = 0
    total_errors: int = 0
    dashboards: list[RouteDashboard] = Field(default_factory=list)
    routes: list[RouteSummary] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


class DashboardsSnapshot(BaseModel):
    """Combined control-plane dashboards snapshot."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    agents: AgentDashboardsSnapshot
    routes: RouteDashboardsSnapshot

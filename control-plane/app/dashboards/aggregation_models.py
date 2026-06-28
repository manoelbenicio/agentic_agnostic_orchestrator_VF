"""Typed models for the aggregated control-plane dashboard.

Each panel is an independent snapshot that composes data from one or more
domain modules.  The top-level ``AggregatedDashboard`` joins all panels
into a single response.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import DashboardHealth


# ---------------------------------------------------------------------------
# Registry panel
# ---------------------------------------------------------------------------

class RegistryAgentSummary(BaseModel):
    """One agent row in the registry panel."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    tenant_id: str
    label: str
    vendor: str
    role: str
    status: str
    workspace_id: str | None = None
    pane_id: str | None = None
    is_active: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RegistryPanel(BaseModel):
    """Registry subsystem snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    total_agents: int = 0
    active_agents: int = 0
    removed_agents: int = 0
    agents: list[RegistryAgentSummary] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Seats / Sessions panel
# ---------------------------------------------------------------------------

class SeatSummary(BaseModel):
    """One persistent seat row."""

    model_config = ConfigDict(extra="forbid")

    seat_id: str
    tenant_id: str
    vendor: str
    display_name: str | None = None
    active: bool = True
    active_session_count: int = 0


class SessionSummary(BaseModel):
    """One login session row."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    seat_id: str
    tenant_id: str
    vendor: str
    status: str
    status_reason: str | None = None
    expires_at: datetime | None = None


class SeatsSessionsPanel(BaseModel):
    """Seats and sessions subsystem snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    total_seats: int = 0
    active_seats: int = 0
    inactive_seats: int = 0
    total_sessions: int = 0
    pending_sessions: int = 0
    degraded_sessions: int = 0
    expired_sessions: int = 0
    seats: list[SeatSummary] = Field(default_factory=list)
    sessions: list[SessionSummary] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Topology panel
# ---------------------------------------------------------------------------

class TopologyNodeSummary(BaseModel):
    """One node from the topology graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    role: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopologyEdgeSummary(BaseModel):
    """One edge from the topology graph."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str


class TopologySquadSnapshot(BaseModel):
    """One squad's topology graph."""

    model_config = ConfigDict(extra="forbid")

    squad_id: str
    node_count: int = 0
    edge_count: int = 0
    nodes: list[TopologyNodeSummary] = Field(default_factory=list)
    edges: list[TopologyEdgeSummary] = Field(default_factory=list)


class TopologyPanel(BaseModel):
    """Topology subsystem snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    total_squads: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    squads: list[TopologySquadSnapshot] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tracing panel
# ---------------------------------------------------------------------------

class TracingAgentBurn(BaseModel):
    """Aggregated burn for one agent across all runtimes."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    total_token_burn: int = 0
    total_seat_seconds: int = 0
    event_count: int = 0


class TracingPanel(BaseModel):
    """Tracing subsystem snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    total_events: int = 0
    total_token_burn: int = 0
    total_seat_seconds: int = 0
    agents: list[TracingAgentBurn] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# FinOps panel
# ---------------------------------------------------------------------------

class FinOpsProjectSummary(BaseModel):
    """Rollup for one tenant/project."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    project_id: str
    total_cost_usd: Decimal = Decimal("0")
    token_cost_usd: Decimal = Decimal("0")
    seat_cost_usd: Decimal = Decimal("0")
    record_count: int = 0


class FinOpsIdleSeatSummary(BaseModel):
    """One idle-seat right-sizing recommendation."""

    model_config = ConfigDict(extra="forbid")

    seat_id: str
    tenant_id: str
    vendor: str
    utilization_pct: Decimal = Decimal("0")
    idle: bool = False
    recommendation: str = "keep"


class FinOpsPanel(BaseModel):
    """FinOps subsystem snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    total_cost_usd: Decimal = Decimal("0")
    token_cost_usd: Decimal = Decimal("0")
    seat_cost_usd: Decimal = Decimal("0")
    total_projects: int = 0
    projects: list[FinOpsProjectSummary] = Field(default_factory=list)
    idle_seats: list[FinOpsIdleSeatSummary] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scheduler / Runtime health panel
# ---------------------------------------------------------------------------

class QuotaVendorSnapshot(BaseModel):
    """Quota position for one vendor."""

    model_config = ConfigDict(extra="forbid")

    vendor: str
    five_hour_cap_seconds: int = 0
    used_five_hour_seconds: int = 0
    five_hour_remaining_seconds: int = 0
    weekly_cap_seconds: int = 0
    used_weekly_seconds: int = 0
    weekly_remaining_seconds: int = 0
    effective_remaining_seconds: int = 0


class SchedulerHealthPanel(BaseModel):
    """Scheduler and runtime health snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    running_count: int = 0
    max_concurrent: int = 0
    queue_depth: int = 0
    concurrency_utilization_pct: float = 0.0
    backoff_events: int = 0
    vendor_quotas: list[QuotaVendorSnapshot] = Field(default_factory=list)
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Coupling health panel
# ---------------------------------------------------------------------------

class CouplingHealthPanel(BaseModel):
    """Herdr / HerdMaster coupling health snapshot."""

    model_config = ConfigDict(extra="forbid")

    health: DashboardHealth = "ok"
    phase: str = "disconnected"
    connected: bool = False
    last_error: str | None = None
    attempts: int = 0
    checked_at: datetime | None = None
    source_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Composed aggregation
# ---------------------------------------------------------------------------

class AggregatedDashboard(BaseModel):
    """Top-level dashboard that composes all aggregation panels."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    overall_health: DashboardHealth = "ok"
    registry: RegistryPanel
    seats_sessions: SeatsSessionsPanel
    topology: TopologyPanel
    tracing: TracingPanel
    finops: FinOpsPanel
    scheduler_health: SchedulerHealthPanel
    coupling_health: CouplingHealthPanel

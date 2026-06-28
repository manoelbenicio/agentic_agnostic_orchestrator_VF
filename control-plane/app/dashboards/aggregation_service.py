"""Aggregation service that composes domain-module data into dashboard panels.

Every ``build_*_panel`` function follows the same pattern:
  1. Read the required repo / object from ``state`` via ``getattr``.
  2. Degrade gracefully when the source is missing or raises.
  3. Return a typed panel with ``health='degraded'`` and ``source_issues``
     populated when partial data is available.

``build_aggregated_dashboard`` composes all panels into a single snapshot.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

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
from .models import DashboardHealth


def build_aggregated_dashboard(state: Any) -> AggregatedDashboard:
    """Compose all panels into a single aggregated dashboard snapshot."""
    generated_at = _now()

    registry = build_registry_panel(state, generated_at=generated_at)
    seats_sessions = build_seats_sessions_panel(state, generated_at=generated_at)
    topology = build_topology_panel(state, generated_at=generated_at)
    tracing = build_tracing_panel(state, generated_at=generated_at)
    finops = build_finops_panel(state, generated_at=generated_at)
    scheduler_health = build_scheduler_health_panel(state, generated_at=generated_at)
    coupling_health = build_coupling_health_panel(state, generated_at=generated_at)

    panel_healths = [
        registry.health,
        seats_sessions.health,
        topology.health,
        tracing.health,
        finops.health,
        scheduler_health.health,
        coupling_health.health,
    ]
    overall = _worst_health(panel_healths)

    return AggregatedDashboard(
        generated_at=generated_at,
        overall_health=overall,
        registry=registry,
        seats_sessions=seats_sessions,
        topology=topology,
        tracing=tracing,
        finops=finops,
        scheduler_health=scheduler_health,
        coupling_health=coupling_health,
    )


# ---------------------------------------------------------------------------
# Registry panel
# ---------------------------------------------------------------------------


def build_registry_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> RegistryPanel:
    """Build the registry agents panel from ``state.registry_repo``."""
    issues: list[str] = []
    repo = getattr(state, "registry_repo", None)
    if repo is None:
        issues.append("registry_repo unavailable")
        return RegistryPanel(health="unavailable", source_issues=issues)

    try:
        agents = list(repo.list_agents())
    except Exception as exc:
        issues.append(f"registry_repo.list_agents failed: {exc}")
        return RegistryPanel(health="degraded", source_issues=issues)

    summaries: list[RegistryAgentSummary] = []
    for agent in agents:
        status = _enum_value(getattr(agent, "status", "unknown"))
        summaries.append(
            RegistryAgentSummary(
                agent_id=str(getattr(agent, "agent_id", "")),
                tenant_id=str(getattr(agent, "tenant_id", "")),
                label=str(getattr(agent, "label", "")),
                vendor=str(getattr(agent, "vendor", "")),
                role=str(getattr(agent, "role", "")),
                status=status,
                workspace_id=getattr(agent, "workspace_id", None),
                pane_id=getattr(agent, "pane_id", None),
                is_active=bool(getattr(agent, "is_active", status == "active")),
                created_at=_safe_dt(getattr(agent, "created_at", None)),
                updated_at=_safe_dt(getattr(agent, "updated_at", None)),
            )
        )

    active = sum(1 for s in summaries if s.is_active)
    return RegistryPanel(
        health="degraded" if issues else "ok",
        total_agents=len(summaries),
        active_agents=active,
        removed_agents=len(summaries) - active,
        agents=summaries,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# Seats / Sessions panel
# ---------------------------------------------------------------------------


def build_seats_sessions_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> SeatsSessionsPanel:
    """Build the seats and sessions panel."""
    issues: list[str] = []

    # --- Seats ---
    seats_repo = getattr(state, "seats_repo", None)
    seat_rows: list[SeatSummary] = []
    if seats_repo is None:
        issues.append("seats_repo unavailable")
    else:
        try:
            raw_seats = list(seats_repo.list())
        except Exception as exc:
            issues.append(f"seats_repo.list failed: {exc}")
            raw_seats = []

        # Active session counts per seat
        sessions_repo = getattr(state, "sessions_repo", None)
        active_counts: dict[str, int] = {}
        if sessions_repo is not None and hasattr(sessions_repo, "active_counts_by_seat"):
            try:
                active_counts = sessions_repo.active_counts_by_seat()
            except Exception as exc:
                issues.append(f"sessions_repo.active_counts_by_seat failed: {exc}")

        for seat in raw_seats:
            seat_id = str(getattr(seat, "seat_id", ""))
            seat_rows.append(
                SeatSummary(
                    seat_id=seat_id,
                    tenant_id=str(getattr(seat, "tenant_id", "")),
                    vendor=str(getattr(seat, "vendor", "")),
                    display_name=getattr(seat, "display_name", None),
                    active=bool(getattr(seat, "active", True)),
                    active_session_count=active_counts.get(seat_id, 0),
                )
            )

    # --- Sessions ---
    sessions_repo = getattr(state, "sessions_repo", None)
    session_rows: list[SessionSummary] = []
    if sessions_repo is None:
        issues.append("sessions_repo unavailable")
    else:
        try:
            raw_sessions = list(sessions_repo.list())
        except Exception as exc:
            issues.append(f"sessions_repo.list failed: {exc}")
            raw_sessions = []

        for session in raw_sessions:
            session_rows.append(
                SessionSummary(
                    session_id=str(getattr(session, "session_id", "")),
                    seat_id=str(getattr(session, "seat_id", "")),
                    tenant_id=str(getattr(session, "tenant_id", "")),
                    vendor=str(getattr(session, "vendor", "")),
                    status=str(getattr(session, "status", "unknown")),
                    status_reason=getattr(session, "status_reason", None),
                    expires_at=_safe_dt(getattr(session, "expires_at", None)),
                )
            )

    active_seats = sum(1 for s in seat_rows if s.active)
    pending = sum(1 for s in session_rows if s.status == "pending")
    degraded_count = sum(1 for s in session_rows if s.status == "degraded")
    expired = sum(1 for s in session_rows if s.status == "expired")

    return SeatsSessionsPanel(
        health="degraded" if issues else "ok",
        total_seats=len(seat_rows),
        active_seats=active_seats,
        inactive_seats=len(seat_rows) - active_seats,
        total_sessions=len(session_rows),
        pending_sessions=pending,
        degraded_sessions=degraded_count,
        expired_sessions=expired,
        seats=seat_rows,
        sessions=session_rows,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# Topology panel
# ---------------------------------------------------------------------------


def build_topology_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> TopologyPanel:
    """Build the topology panel from ``state.topology_repo``."""
    issues: list[str] = []
    repo = getattr(state, "topology_repo", None)
    if repo is None:
        issues.append("topology_repo unavailable")
        return TopologyPanel(health="unavailable", source_issues=issues)

    # Topology snapshots are keyed by squad_id.  We need the list of active
    # squads.  The topology_repo does not expose a list_all method, but we
    # can derive squad_ids from the registry agents (each has a tenant_id
    # that maps to a squad), or from a squad_api if available.
    squad_ids: list[str] = []
    squad_api = getattr(state, "squad_repo", None) or getattr(state, "projects_repo", None)
    if squad_api is not None and hasattr(squad_api, "list"):
        try:
            projects = list(squad_api.list())
            for project in projects:
                pid = str(getattr(project, "project_id", getattr(project, "squad_id", "")))
                if pid:
                    squad_ids.append(pid)
        except Exception as exc:
            issues.append(f"project/squad list for topology failed: {exc}")

    # Also try to derive from registry agents' tenant_ids
    registry_repo = getattr(state, "registry_repo", None)
    if registry_repo is not None and not squad_ids:
        try:
            agents = list(registry_repo.list_agents())
            seen: set[str] = set()
            for agent in agents:
                tid = str(getattr(agent, "tenant_id", ""))
                if tid and tid not in seen:
                    seen.add(tid)
                    squad_ids.append(tid)
        except Exception as exc:
            issues.append(f"registry for topology squad discovery failed: {exc}")

    squads: list[TopologySquadSnapshot] = []
    total_nodes = 0
    total_edges = 0
    for squad_id in squad_ids:
        try:
            topo = repo.get_topology(squad_id)
        except Exception as exc:
            issues.append(f"topology_repo.get_topology({squad_id}) failed: {exc}")
            continue
        if topo is None:
            continue
        raw_nodes = topo.get("nodes", []) if isinstance(topo, dict) else []
        raw_edges = topo.get("edges", []) if isinstance(topo, dict) else []
        nodes = [
            TopologyNodeSummary(
                id=str(_dict_get(n, "id", "")),
                role=str(_dict_get(n, "role", "")),
                metadata={k: v for k, v in (n if isinstance(n, dict) else {}).items() if k not in ("id", "role")},
            )
            for n in raw_nodes
        ]
        edges = [
            TopologyEdgeSummary(
                source=str(_dict_get(e, "source", "")),
                target=str(_dict_get(e, "target", "")),
            )
            for e in raw_edges
        ]
        total_nodes += len(nodes)
        total_edges += len(edges)
        squads.append(
            TopologySquadSnapshot(
                squad_id=squad_id,
                node_count=len(nodes),
                edge_count=len(edges),
                nodes=nodes,
                edges=edges,
            )
        )

    return TopologyPanel(
        health="degraded" if issues else "ok",
        total_squads=len(squads),
        total_nodes=total_nodes,
        total_edges=total_edges,
        squads=squads,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# Tracing panel
# ---------------------------------------------------------------------------


def build_tracing_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> TracingPanel:
    """Build the tracing panel from ``state.trace_repo``."""
    issues: list[str] = []
    repo = getattr(state, "trace_repo", None)
    if repo is None:
        issues.append("trace_repo unavailable")
        return TracingPanel(health="unavailable", source_issues=issues)

    if not hasattr(repo, "burn_by_agent_runtime"):
        issues.append("trace_repo.burn_by_agent_runtime unavailable")
        return TracingPanel(health="degraded", source_issues=issues)

    try:
        rows = list(repo.burn_by_agent_runtime())
    except Exception as exc:
        issues.append(f"trace_repo.burn_by_agent_runtime failed: {exc}")
        return TracingPanel(health="degraded", source_issues=issues)

    # Aggregate across runtimes per agent
    agent_burns: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        agent_id = str(_row_get(row, "agent_id", "unknown"))
        agent_burns[agent_id]["total_token_burn"] += int(_row_get(row, "token_burn", 0) or 0)
        agent_burns[agent_id]["total_seat_seconds"] += int(_row_get(row, "seat_seconds", 0) or 0)
        agent_burns[agent_id]["event_count"] += int(_row_get(row, "event_count", 0) or 0)

    agents = [
        TracingAgentBurn(
            agent_id=agent_id,
            total_token_burn=burns["total_token_burn"],
            total_seat_seconds=burns["total_seat_seconds"],
            event_count=burns["event_count"],
        )
        for agent_id, burns in sorted(agent_burns.items())
    ]

    return TracingPanel(
        health="ok",
        total_events=sum(a.event_count for a in agents),
        total_token_burn=sum(a.total_token_burn for a in agents),
        total_seat_seconds=sum(a.total_seat_seconds for a in agents),
        agents=agents,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# FinOps panel
# ---------------------------------------------------------------------------


def build_finops_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> FinOpsPanel:
    """Build the FinOps panel from ``state.finops_repo``."""
    issues: list[str] = []
    repo = getattr(state, "finops_repo", None)
    if repo is None:
        issues.append("finops_repo unavailable")
        return FinOpsPanel(health="unavailable", source_issues=issues)

    # --- Project rollups ---
    projects_list: list[tuple[str, str]] = []
    if hasattr(repo, "list_projects"):
        try:
            projects_list = list(repo.list_projects())
        except Exception as exc:
            issues.append(f"finops_repo.list_projects failed: {exc}")

    project_summaries: list[FinOpsProjectSummary] = []
    total_cost = Decimal("0")
    token_cost = Decimal("0")
    seat_cost = Decimal("0")
    for tenant_id, project_id in projects_list:
        try:
            rollup = repo.rollup_project(tenant_id, project_id)
            summary = FinOpsProjectSummary(
                tenant_id=tenant_id,
                project_id=project_id,
                total_cost_usd=rollup.total_cost_usd,
                token_cost_usd=rollup.token_cost_usd,
                seat_cost_usd=rollup.seat_cost_usd,
                record_count=rollup.record_count,
            )
            project_summaries.append(summary)
            total_cost += rollup.total_cost_usd
            token_cost += rollup.token_cost_usd
            seat_cost += rollup.seat_cost_usd
        except Exception as exc:
            issues.append(f"finops_repo.rollup_project({tenant_id}/{project_id}) failed: {exc}")

    # --- Idle seat recommendations ---
    idle_seats: list[FinOpsIdleSeatSummary] = []
    if hasattr(repo, "idle_seat_recommendations"):
        # Gather unique tenant_ids from projects or from registry
        tenant_ids: set[str] = {t for t, _ in projects_list}
        if not tenant_ids:
            registry_repo = getattr(state, "registry_repo", None)
            if registry_repo is not None:
                try:
                    for agent in registry_repo.list_agents():
                        tenant_ids.add(str(getattr(agent, "tenant_id", "")))
                except Exception:
                    pass  # best-effort
        for tenant_id in sorted(tenant_ids):
            if not tenant_id:
                continue
            try:
                recs = repo.idle_seat_recommendations(tenant_id=tenant_id)
                for rec in recs:
                    idle_seats.append(
                        FinOpsIdleSeatSummary(
                            seat_id=str(getattr(rec, "seat_id", "")),
                            tenant_id=str(getattr(rec, "tenant_id", "")),
                            vendor=str(getattr(rec, "vendor", "")),
                            utilization_pct=getattr(rec, "utilization_pct", Decimal("0")),
                            idle=bool(getattr(rec, "idle", False)),
                            recommendation=str(getattr(rec, "recommendation", "keep")),
                        )
                    )
            except Exception as exc:
                issues.append(f"finops_repo.idle_seat_recommendations({tenant_id}) failed: {exc}")

    return FinOpsPanel(
        health="degraded" if issues else "ok",
        total_cost_usd=total_cost,
        token_cost_usd=token_cost,
        seat_cost_usd=seat_cost,
        total_projects=len(project_summaries),
        projects=project_summaries,
        idle_seats=idle_seats,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# Scheduler / Runtime health panel
# ---------------------------------------------------------------------------


def build_scheduler_health_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> SchedulerHealthPanel:
    """Build the scheduler and runtime health panel."""
    issues: list[str] = []
    scheduler = getattr(state, "scheduler", None)
    if scheduler is None:
        issues.append("scheduler unavailable")
        return SchedulerHealthPanel(health="unavailable", source_issues=issues)

    running = int(getattr(scheduler, "running_count", 0))
    max_conc = int(getattr(scheduler, "max_concurrent", 0))
    queue_obj = getattr(scheduler, "queue", None)
    queue_depth = len(queue_obj) if queue_obj is not None else 0
    backoff_log = getattr(scheduler, "backoff_log", [])
    backoff_events = len(backoff_log) if backoff_log else 0
    utilization = (running / max_conc * 100.0) if max_conc > 0 else 0.0

    # --- Vendor quota snapshots ---
    vendor_quotas: list[QuotaVendorSnapshot] = []
    quota_ledger = getattr(scheduler, "quota", None)
    if quota_ledger is not None:
        snapshots = getattr(quota_ledger, "_snapshots", {})
        for vendor, snap in sorted(snapshots.items()):
            vendor_quotas.append(
                QuotaVendorSnapshot(
                    vendor=str(vendor),
                    five_hour_cap_seconds=int(getattr(snap, "five_hour_cap_seconds", 0)),
                    used_five_hour_seconds=int(getattr(snap, "used_five_hour_seconds", 0)),
                    five_hour_remaining_seconds=int(getattr(snap, "five_hour_remaining_seconds", 0)),
                    weekly_cap_seconds=int(getattr(snap, "weekly_cap_seconds", 0)),
                    used_weekly_seconds=int(getattr(snap, "used_weekly_seconds", 0)),
                    weekly_remaining_seconds=int(getattr(snap, "weekly_remaining_seconds", 0)),
                    effective_remaining_seconds=int(getattr(snap, "effective_remaining_seconds", 0)),
                )
            )

    # Determine health
    health: DashboardHealth = "ok"
    if utilization >= 90.0 or queue_depth > 0:
        health = "degraded"
    if issues:
        health = "degraded"

    return SchedulerHealthPanel(
        health=health,
        running_count=running,
        max_concurrent=max_conc,
        queue_depth=queue_depth,
        concurrency_utilization_pct=round(utilization, 2),
        backoff_events=backoff_events,
        vendor_quotas=vendor_quotas,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# Coupling health panel
# ---------------------------------------------------------------------------


def build_coupling_health_panel(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> CouplingHealthPanel:
    """Build the coupling health panel from ``state.coupling_status``."""
    issues: list[str] = []
    coupling = getattr(state, "coupling_status", None)
    if coupling is None:
        issues.append("coupling_status unavailable")
        return CouplingHealthPanel(health="unavailable", source_issues=issues)

    phase = str(_enum_value(getattr(coupling, "phase", "disconnected")))
    connected = bool(getattr(coupling, "connected", False))
    last_error = getattr(coupling, "last_error", None)
    attempts = int(getattr(coupling, "attempts", 0))
    checked_at = _safe_dt(getattr(coupling, "checked_at", None))

    if phase == "connected":
        health: DashboardHealth = "ok"
    elif phase == "degraded":
        health = "degraded"
    else:
        health = "unavailable"

    return CouplingHealthPanel(
        health=health,
        phase=phase,
        connected=connected,
        last_error=last_error,
        attempts=attempts,
        checked_at=checked_at,
        source_issues=issues,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _worst_health(healths: list[DashboardHealth]) -> DashboardHealth:
    """Return the worst health among all panels."""
    if "unavailable" in healths:
        return "unavailable"
    if "degraded" in healths:
        return "degraded"
    return "ok"


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _dict_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _safe_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

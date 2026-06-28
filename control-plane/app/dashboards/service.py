"""Snapshot builders for dashboard routes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from fastapi.routing import APIRoute

from .models import (
    AgentDashboardDetail,
    AgentDashboardSummary,
    AgentDashboardsSnapshot,
    DashboardsSnapshot,
    RouteDashboard,
    RouteDashboardsSnapshot,
    RouteSummary,
)


ACTIVE_TASK_STATUSES = {"pending", "working", "review", "held", "blocked", "orphaned"}


class AgentDashboardNotFoundError(LookupError):
    """Raised when an agent dashboard target cannot be found."""


class DashboardScopeViolationError(PermissionError):
    """Raised when tenant/project scope does not allow the requested agent."""


class DashboardScopeSourceUnavailableError(RuntimeError):
    """Raised when a source required for scope enforcement is unavailable."""


def build_dashboards_snapshot(state: Any, *, routes: Iterable[Any] = ()) -> DashboardsSnapshot:
    generated_at = _now()
    return DashboardsSnapshot(
        generated_at=generated_at,
        agents=build_agent_dashboards_snapshot(state, generated_at=generated_at),
        routes=build_route_dashboards_snapshot(routes, state=state, generated_at=generated_at),
    )


def build_agent_dashboard_detail(
    state: Any,
    agent_id: str,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    generated_at: datetime | None = None,
) -> AgentDashboardDetail:
    generated_at = generated_at or _now()
    source_issues: list[str] = []
    agent = _get_agent(state, agent_id)
    effective_tenant_id = tenant_id or str(getattr(agent, "tenant_id", ""))
    _check_agent_tenant_scope(agent, effective_tenant_id)
    _check_project_scope(state, agent, effective_tenant_id, project_id)

    summary = _agent_summary(
        agent,
        _task_stats_for_agent(
            state,
            agent_id,
            tenant_id=effective_tenant_id,
            project_id=project_id,
            issues=source_issues,
        ),
        _trace_stats_for_agent(
            state,
            agent_id,
            tenant_id=effective_tenant_id,
            project_id=project_id,
            issues=source_issues,
        ),
        _cost_stats_for_agent(
            state,
            agent_id,
            tenant_id=effective_tenant_id,
            project_id=project_id,
            issues=source_issues,
        ),
    )
    return AgentDashboardDetail(
        generated_at=generated_at,
        health="degraded" if source_issues else "ok",
        tenant_id=effective_tenant_id,
        project_id=project_id,
        agent=summary,
        source_issues=source_issues,
    )


def build_agent_dashboards_snapshot(
    state: Any,
    *,
    generated_at: datetime | None = None,
) -> AgentDashboardsSnapshot:
    generated_at = generated_at or _now()
    source_issues: list[str] = []
    agents = _list_agents(state, source_issues)
    task_stats = _task_stats(state, source_issues)
    trace_stats = _trace_stats(state, source_issues)
    cost_stats = _cost_stats(state, source_issues)

    summaries: list[AgentDashboardSummary] = []
    for agent in agents:
        current_agent_id = str(getattr(agent, "agent_id"))
        summaries.append(
            _agent_summary(
                agent,
                task_stats.get(current_agent_id, {}),
                trace_stats.get(current_agent_id, {}),
                cost_stats.get(current_agent_id, {}),
            )
        )

    summaries.sort(key=lambda item: (not item.active, item.agent_id))
    return AgentDashboardsSnapshot(
        generated_at=generated_at,
        health="degraded" if source_issues else "ok",
        total_agents=len(summaries),
        active_agents=sum(1 for item in summaries if item.active),
        total_tasks=sum(item.task_count for item in summaries),
        active_tasks=sum(item.active_task_count for item in summaries),
        total_token_burn=sum(item.token_burn for item in summaries),
        total_seat_seconds=sum(item.seat_seconds for item in summaries),
        total_cost_usd=sum((item.total_cost_usd for item in summaries), Decimal("0")),
        agents=summaries,
        source_issues=source_issues,
    )


def build_route_dashboards_snapshot(
    routes: Iterable[Any],
    *,
    state: Any | None = None,
    squad: str | None = None,
    source_agent: str | None = None,
    target_agent: str | None = None,
    status: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    generated_at: datetime | None = None,
) -> RouteDashboardsSnapshot:
    import copy
    generated_at = generated_at or _now()
    source_issues: list[str] = []

    flat_routes: list[APIRoute] = []

    def flatten(route_list: Iterable[Any], parent_prefix: str = "") -> None:
        for r in route_list:
            if hasattr(r, "original_router"):
                prefix = getattr(r.include_context, "prefix", "")
                combined_prefix = parent_prefix + prefix
                nested_routes = getattr(r.original_router, "routes", [])
                flatten(nested_routes, parent_prefix=combined_prefix)
            elif isinstance(r, APIRoute):
                r_copy = copy.copy(r)
                prefix_clean = parent_prefix.rstrip("/")
                r_copy.path = prefix_clean + r.path
                flat_routes.append(r_copy)

    flatten(routes)

    summaries = [_route_summary(route) for route in flat_routes]
    effective_tenant_id = _effective_tenant_for_project_scope(state, tenant_id, project_id)
    summaries.extend(
        _topology_route_summaries(
            state,
            squad=squad,
            tenant_id=effective_tenant_id,
            project_id=project_id,
            issues=source_issues,
            require_source=any([squad, source_agent, target_agent, effective_tenant_id, project_id]),
        )
    )
    summaries = _filter_route_summaries(
        summaries,
        squad=squad,
        source_agent=source_agent,
        target_agent=target_agent,
        status=status,
        tenant_id=effective_tenant_id,
        project_id=project_id,
    )
    summaries.sort(key=lambda route: (route.path, route.methods))

    grouped: dict[str, list[RouteSummary]] = defaultdict(list)
    for route in summaries:
        dashboard_id = route.tags[0] if route.tags else _route_family(route.path)
        grouped[dashboard_id].append(route)

    dashboards = [
        _route_dashboard(dashboard_id, routes)
        for dashboard_id, routes in sorted(grouped.items(), key=lambda item: item[0])
    ]
    return RouteDashboardsSnapshot(
        generated_at=generated_at,
        health="degraded" if source_issues else "ok",
        total_routes=len(summaries),
        total_requests=sum(item.request_count for item in summaries),
        total_errors=sum(item.error_count for item in summaries),
        dashboards=dashboards,
        routes=summaries,
        source_issues=source_issues,
    )


def _list_agents(state: Any, issues: list[str]) -> list[Any]:
    repo = getattr(state, "registry_repo", None)
    if repo is None:
        issues.append("registry_repo unavailable")
        return []
    try:
        return list(repo.list_agents())
    except Exception as exc:  # pragma: no cover - defensive degradation path
        issues.append(f"registry_repo.list_agents failed: {exc}")
        return []


def _get_agent(state: Any, agent_id: str) -> Any:
    repo = getattr(state, "registry_repo", None)
    if repo is None:
        raise DashboardScopeSourceUnavailableError("registry_repo unavailable")
    try:
        agent = repo.get(agent_id) if hasattr(repo, "get") else None
    except Exception as exc:
        raise DashboardScopeSourceUnavailableError(f"registry_repo.get failed: {exc}") from exc
    if agent is None and hasattr(repo, "list_agents"):
        try:
            agent = next((item for item in repo.list_agents() if str(getattr(item, "agent_id", "")) == agent_id), None)
        except Exception as exc:
            raise DashboardScopeSourceUnavailableError(f"registry_repo.list_agents failed: {exc}") from exc
    if agent is None:
        raise AgentDashboardNotFoundError(agent_id)
    return agent


def _check_agent_tenant_scope(agent: Any, tenant_id: str) -> None:
    agent_tenant_id = str(getattr(agent, "tenant_id", ""))
    if tenant_id and agent_tenant_id != tenant_id:
        raise DashboardScopeViolationError(
            f"agent belongs to tenant {agent_tenant_id!r}, not requested tenant {tenant_id!r}"
        )


def _check_project_scope(state: Any, agent: Any, tenant_id: str, project_id: str | None) -> None:
    if project_id is None:
        return
    repo = getattr(state, "projects_repo", None)
    if repo is None or not hasattr(repo, "get"):
        raise DashboardScopeSourceUnavailableError("projects_repo unavailable for project scope check")
    try:
        project = repo.get(project_id)
    except Exception as exc:
        raise DashboardScopeSourceUnavailableError(f"projects_repo.get failed: {exc}") from exc
    if project is None:
        raise AgentDashboardNotFoundError(f"project {project_id}")
    project_tenant_id = str(getattr(project, "tenant_id", ""))
    agent_tenant_id = str(getattr(agent, "tenant_id", ""))
    if project_tenant_id != tenant_id or project_tenant_id != agent_tenant_id:
        raise DashboardScopeViolationError(
            f"project belongs to tenant {project_tenant_id!r}, not agent tenant {agent_tenant_id!r}"
        )


def _agent_summary(
    agent: Any,
    tasks: dict[str, Any],
    traces: dict[str, Any],
    costs: dict[str, Any],
) -> AgentDashboardSummary:
    agent_id = str(getattr(agent, "agent_id"))
    status = _enum_value(getattr(agent, "status", "unknown"))
    return AgentDashboardSummary(
        agent_id=agent_id,
        tenant_id=str(getattr(agent, "tenant_id", "")),
        label=str(getattr(agent, "label", agent_id)),
        vendor=str(getattr(agent, "vendor", "")),
        role=str(getattr(agent, "role", "")),
        status=status,
        workspace_id=getattr(agent, "workspace_id", None),
        pane_id=getattr(agent, "pane_id", None),
        active=bool(getattr(agent, "is_active", status == "active")),
        task_count=int(tasks.get("task_count", 0)),
        active_task_count=int(tasks.get("active_task_count", 0)),
        done_task_count=int(tasks.get("done_task_count", 0)),
        blocked_task_count=int(tasks.get("blocked_task_count", 0)),
        token_burn=int(traces.get("token_burn", 0)),
        seat_seconds=int(traces.get("seat_seconds", 0)),
        trace_event_count=int(traces.get("trace_event_count", 0)),
        total_cost_usd=Decimal(str(costs.get("total_cost_usd", "0"))),
        token_cost_usd=Decimal(str(costs.get("token_cost_usd", "0"))),
        seat_cost_usd=Decimal(str(costs.get("seat_cost_usd", "0"))),
        last_seen_at=_latest(
            getattr(agent, "updated_at", None),
            tasks.get("last_seen_at"),
            traces.get("last_seen_at"),
        ),
        metadata=dict(getattr(agent, "metadata", {}) or {}),
    )


def _task_stats(state: Any, issues: list[str]) -> dict[str, dict[str, Any]]:
    repo = getattr(state, "tasks_repo", None)
    if repo is None:
        return {}
    try:
        tasks = list(repo.list())
    except Exception as exc:  # pragma: no cover - defensive degradation path
        issues.append(f"tasks_repo.list failed: {exc}")
        return {}

    stats: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    for task in tasks:
        agent_id = str(getattr(task, "agent", "unknown"))
        status = _enum_value(getattr(task, "status", "unknown"))
        stats[agent_id]["task_count"] += 1
        if status in ACTIVE_TASK_STATUSES:
            stats[agent_id]["active_task_count"] += 1
        if status == "done":
            stats[agent_id]["done_task_count"] += 1
        if status == "blocked":
            stats[agent_id]["blocked_task_count"] += 1
        stats[agent_id]["last_seen_at"] = _latest(
            stats[agent_id].get("last_seen_at"),
            getattr(task, "last_seen_at", None),
            getattr(task, "updated_at", None),
            getattr(task, "created_at", None),
        )
    return {agent_id: dict(values) for agent_id, values in stats.items()}


def _task_stats_for_agent(
    state: Any,
    agent_id: str,
    *,
    tenant_id: str,
    project_id: str | None,
    issues: list[str],
) -> dict[str, Any]:
    repo = getattr(state, "tasks_repo", None)
    if repo is None:
        return {}
    try:
        try:
            tasks = list(repo.list(agent=agent_id))
        except TypeError:
            tasks = [task for task in repo.list() if str(getattr(task, "agent", "")) == agent_id]
    except Exception as exc:  # pragma: no cover - defensive degradation path
        issues.append(f"tasks_repo.list failed: {exc}")
        return {}

    scoped_tasks = []
    omitted_for_scope = 0
    for task in tasks:
        metadata = dict(getattr(task, "metadata", {}) or {})
        task_tenant_id = metadata.get("tenant_id")
        task_project_id = metadata.get("project_id")
        if task_tenant_id is not None and str(task_tenant_id) != tenant_id:
            continue
        if project_id is not None:
            if task_project_id is None:
                omitted_for_scope += 1
                continue
            if str(task_project_id) != project_id:
                continue
        scoped_tasks.append(task)
    if project_id is not None and omitted_for_scope:
        issues.append("tasks source lacks project_id for some agent tasks; omitted unscoped task rows")

    return _task_stats_from_records(scoped_tasks).get(agent_id, {})


def _trace_stats(state: Any, issues: list[str]) -> dict[str, dict[str, Any]]:
    repo = getattr(state, "trace_repo", None)
    if repo is None or not hasattr(repo, "burn_by_agent_runtime"):
        return {}
    try:
        rows = list(repo.burn_by_agent_runtime())
    except Exception as exc:  # pragma: no cover - defensive degradation path
        issues.append(f"trace_repo.burn_by_agent_runtime failed: {exc}")
        return {}

    stats: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        agent_id = str(_row_get(row, "agent_id", "unknown"))
        stats[agent_id]["token_burn"] += int(_row_get(row, "token_burn", 0) or 0)
        stats[agent_id]["seat_seconds"] += int(_row_get(row, "seat_seconds", 0) or 0)
        stats[agent_id]["trace_event_count"] += int(_row_get(row, "event_count", 0) or 0)
    return {agent_id: dict(values) for agent_id, values in stats.items()}


def _trace_stats_for_agent(
    state: Any,
    agent_id: str,
    *,
    tenant_id: str,
    project_id: str | None,
    issues: list[str],
) -> dict[str, Any]:
    repo = getattr(state, "trace_repo", None)
    if repo is None:
        return {}
    if hasattr(repo, "by_agent"):
        try:
            events = list(repo.by_agent(agent_id))
        except Exception as exc:  # pragma: no cover - defensive degradation path
            issues.append(f"trace_repo.by_agent failed: {exc}")
            return {}
        token_burn = 0
        seat_seconds = 0
        event_count = 0
        last_seen_at: datetime | None = None
        for event in events:
            if str(getattr(event, "tenant_id", "")) != tenant_id:
                continue
            if project_id is not None and str(getattr(event, "project_id", "")) != project_id:
                continue
            token_burn += int(getattr(event, "token_burn", 0) or 0)
            seat_seconds += int(getattr(event, "seat_seconds", 0) or 0)
            event_count += 1
            last_seen_at = _latest(last_seen_at, getattr(event, "occurred_at", None))
        return {
            "token_burn": token_burn,
            "seat_seconds": seat_seconds,
            "trace_event_count": event_count,
            "last_seen_at": last_seen_at,
        }
    if project_id is not None:
        issues.append("trace source cannot enforce project scope; omitted trace metrics")
        return {}
    return _trace_stats(state, issues).get(agent_id, {})


def _cost_stats(state: Any, issues: list[str]) -> dict[str, dict[str, Decimal]]:
    repo = getattr(state, "finops_repo", None)
    if repo is None or not hasattr(repo, "list_projects") or not hasattr(repo, "rollup_by_dimension"):
        return {}
    try:
        projects = list(repo.list_projects())
    except Exception as exc:  # pragma: no cover - defensive degradation path
        issues.append(f"finops_repo.list_projects failed: {exc}")
        return {}

    stats: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
    for tenant_id, project_id in projects:
        try:
            buckets = repo.rollup_by_dimension(tenant_id, project_id, "agent_id")
        except Exception as exc:  # pragma: no cover - defensive degradation path
            issues.append(f"finops_repo.rollup_by_dimension failed for {tenant_id}/{project_id}: {exc}")
            continue
        for bucket in buckets:
            agent_id = str(getattr(bucket, "key", "unknown"))
            stats[agent_id]["total_cost_usd"] += Decimal(str(getattr(bucket, "total_cost_usd", "0")))
            stats[agent_id]["token_cost_usd"] += Decimal(str(getattr(bucket, "token_cost_usd", "0")))
            stats[agent_id]["seat_cost_usd"] += Decimal(str(getattr(bucket, "seat_cost_usd", "0")))
    return {agent_id: dict(values) for agent_id, values in stats.items()}


def _cost_stats_for_agent(
    state: Any,
    agent_id: str,
    *,
    tenant_id: str,
    project_id: str | None,
    issues: list[str],
) -> dict[str, Decimal]:
    repo = getattr(state, "finops_repo", None)
    if repo is None or not hasattr(repo, "rollup_by_dimension"):
        return {}
    if project_id is None:
        return _cost_stats(state, issues).get(agent_id, {})
    try:
        buckets = repo.rollup_by_dimension(tenant_id, project_id, "agent_id")
    except Exception as exc:  # pragma: no cover - defensive degradation path
        issues.append(f"finops_repo.rollup_by_dimension failed for {tenant_id}/{project_id}: {exc}")
        return {}
    for bucket in buckets:
        if str(getattr(bucket, "key", "unknown")) == agent_id:
            return {
                "total_cost_usd": Decimal(str(getattr(bucket, "total_cost_usd", "0"))),
                "token_cost_usd": Decimal(str(getattr(bucket, "token_cost_usd", "0"))),
                "seat_cost_usd": Decimal(str(getattr(bucket, "seat_cost_usd", "0"))),
            }
    return {}


def _task_stats_from_records(tasks: Iterable[Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    for task in tasks:
        agent_id = str(getattr(task, "agent", "unknown"))
        status = _enum_value(getattr(task, "status", "unknown"))
        stats[agent_id]["task_count"] += 1
        if status in ACTIVE_TASK_STATUSES:
            stats[agent_id]["active_task_count"] += 1
        if status == "done":
            stats[agent_id]["done_task_count"] += 1
        if status == "blocked":
            stats[agent_id]["blocked_task_count"] += 1
        stats[agent_id]["last_seen_at"] = _latest(
            stats[agent_id].get("last_seen_at"),
            getattr(task, "last_seen_at", None),
            getattr(task, "updated_at", None),
            getattr(task, "created_at", None),
        )
    return {agent_id: dict(values) for agent_id, values in stats.items()}


def _effective_tenant_for_project_scope(
    state: Any | None,
    tenant_id: str | None,
    project_id: str | None,
) -> str | None:
    if project_id is None:
        return tenant_id
    repo = getattr(state, "projects_repo", None)
    if repo is None or not hasattr(repo, "get"):
        raise DashboardScopeSourceUnavailableError("projects_repo unavailable for project scope check")
    try:
        project = repo.get(project_id)
    except Exception as exc:
        raise DashboardScopeSourceUnavailableError(f"projects_repo.get failed: {exc}") from exc
    if project is None:
        raise AgentDashboardNotFoundError(f"project {project_id}")
    project_tenant_id = str(getattr(project, "tenant_id", ""))
    if tenant_id is not None and tenant_id != project_tenant_id:
        raise DashboardScopeViolationError(
            f"project belongs to tenant {project_tenant_id!r}, not requested tenant {tenant_id!r}"
        )
    return project_tenant_id


def _topology_route_summaries(
    state: Any | None,
    *,
    squad: str | None,
    tenant_id: str | None,
    project_id: str | None,
    issues: list[str],
    require_source: bool = False,
) -> list[RouteSummary]:
    if state is None:
        return []
    repo = getattr(state, "topology_repo", None)
    if repo is None or not hasattr(repo, "get_topology"):
        if require_source:
            issues.append("topology_repo unavailable")
        return []

    summaries: list[RouteSummary] = []
    discovered_squads = _discover_route_squads(
        state,
        squad=squad,
        tenant_id=tenant_id,
        project_id=project_id,
        issues=issues,
    )
    if require_source and not discovered_squads:
        issues.append("route squad discovery unavailable")

    for squad_id, route_tenant_id, route_project_id in discovered_squads:
        try:
            topology = repo.get_topology(squad_id)
        except Exception as exc:  # pragma: no cover - defensive degradation path
            issues.append(f"topology_repo.get_topology({squad_id}) failed: {exc}")
            continue
        if topology is None:
            continue
        nodes = {
            str(node.get("id")): dict(node)
            for node in topology.get("nodes", [])
            if isinstance(node, dict) and node.get("id") is not None
        }
        for edge in topology.get("edges", []):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if not source or not target:
                continue
            edge_status = _route_status(edge.get("status", "ok"))
            route_id = str(edge.get("id") or f"{squad_id}:{source}->{target}")
            summaries.append(
                RouteSummary(
                    route_id=route_id,
                    path=f"/squads/{squad_id}/routes/{source}->{target}",
                    methods=["MESSAGE"],
                    name=str(edge.get("label") or f"{source} to {target}"),
                    tags=["agent-routes", "squads"],
                    tenant_id=route_tenant_id,
                    project_id=route_project_id,
                    squad_id=squad_id,
                    source_agent=source,
                    target_agent=target,
                    status=edge_status,
                    request_count=int(edge.get("request_count", 0) or 0),
                    error_count=int(edge.get("error_count", 0) or 0),
                    error_rate=float(edge.get("error_rate", 0.0) or 0.0),
                    p95_latency_ms=_optional_float(edge.get("p95_latency_ms")),
                    last_seen_at=_coerce_datetime(edge.get("last_seen_at")),
                    # Include node existence through status instead of widening the response schema.
                )
            )
            if source not in nodes or target not in nodes:
                issues.append(f"topology edge {route_id} references missing node")
    return summaries


def _discover_route_squads(
    state: Any,
    *,
    squad: str | None,
    tenant_id: str | None,
    project_id: str | None,
    issues: list[str],
) -> list[tuple[str, str | None, str | None]]:
    if squad is not None:
        return [(squad, tenant_id, project_id)]
    if project_id is not None:
        return [(project_id, tenant_id, project_id)]

    discovered: dict[str, tuple[str | None, str | None]] = {}
    projects_repo = getattr(state, "projects_repo", None)
    if projects_repo is not None and hasattr(projects_repo, "list"):
        try:
            projects = list(projects_repo.list(tenant_id=tenant_id)) if tenant_id else list(projects_repo.list())
            for project in projects:
                pid = str(getattr(project, "project_id", ""))
                if pid:
                    discovered[pid] = (str(getattr(project, "tenant_id", "")) or tenant_id, pid)
        except Exception as exc:  # pragma: no cover - defensive degradation path
            issues.append(f"projects_repo.list failed for route scope discovery: {exc}")

    registry_repo = getattr(state, "registry_repo", None)
    if not discovered and registry_repo is not None and hasattr(registry_repo, "list_agents"):
        try:
            for agent in registry_repo.list_agents(tenant_id=tenant_id) if tenant_id else registry_repo.list_agents():
                squad_id = str(getattr(agent, "metadata", {}).get("squad_id") or getattr(agent, "tenant_id", ""))
                if squad_id:
                    discovered.setdefault(squad_id, (str(getattr(agent, "tenant_id", "")) or tenant_id, None))
        except Exception as exc:  # pragma: no cover - defensive degradation path
            issues.append(f"registry_repo.list_agents failed for route scope discovery: {exc}")

    return [
        (squad_id, values[0], values[1])
        for squad_id, values in sorted(discovered.items(), key=lambda item: item[0])
    ]


def _filter_route_summaries(
    routes: Iterable[RouteSummary],
    *,
    squad: str | None,
    source_agent: str | None,
    target_agent: str | None,
    status: str | None,
    tenant_id: str | None,
    project_id: str | None,
) -> list[RouteSummary]:
    filtered: list[RouteSummary] = []
    normalized_status = status.lower() if status else None
    for route in routes:
        if squad is not None and route.squad_id != squad:
            continue
        if source_agent is not None and route.source_agent != source_agent:
            continue
        if target_agent is not None and route.target_agent != target_agent:
            continue
        if tenant_id is not None and route.tenant_id != tenant_id:
            continue
        if project_id is not None and route.project_id != project_id:
            continue
        if normalized_status is not None and route.status.lower() != normalized_status:
            continue
        filtered.append(route)
    return filtered


def _route_summary(route: APIRoute) -> RouteSummary:
    methods = sorted(method for method in route.methods if method not in {"HEAD", "OPTIONS"})
    return RouteSummary(
        route_id=f"{','.join(methods)} {route.path}",
        path=route.path,
        methods=methods,
        name=route.name,
        tags=[str(tag) for tag in route.tags],
    )


def _route_dashboard(dashboard_id: str, routes: list[RouteSummary]) -> RouteDashboard:
    request_count = sum(route.request_count for route in routes)
    error_count = sum(route.error_count for route in routes)
    return RouteDashboard(
        dashboard_id=dashboard_id,
        title=f"{dashboard_id.replace('_', ' ').replace('-', ' ').title()} Routes",
        route_count=len(routes),
        request_count=request_count,
        error_count=error_count,
        error_rate=(error_count / request_count) if request_count else 0.0,
        routes=routes,
    )


def _route_family(path: str) -> str:
    parts = [part for part in path.split("/") if part and not part.startswith("{")]
    if parts and parts[0] == "api" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else "root"


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _route_status(value: Any) -> str:
    raw = str(getattr(value, "value", value)).strip().lower()
    if raw in {"ok", "active", "enabled", "allowed", "healthy"}:
        return "ok"
    if raw in {"degraded", "warning", "blocked", "limited"}:
        return "degraded"
    if raw in {"unavailable", "down", "disabled", "failed", "error"}:
        return "unavailable"
    return "ok"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _latest(*values: Any) -> datetime | None:
    timestamps = [value for value in values if isinstance(value, datetime)]
    return max(timestamps) if timestamps else None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

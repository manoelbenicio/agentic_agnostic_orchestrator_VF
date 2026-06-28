from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from app.dashboards import build_agent_dashboard_detail, build_dashboards_router
from app.dashboards.service import DashboardScopeViolationError, build_route_dashboards_snapshot


@dataclass(frozen=True)
class FakeAgent:
    agent_id: str
    tenant_id: str
    label: str
    vendor: str
    role: str
    status: str = "active"
    workspace_id: str | None = "workspace-main"
    pane_id: str | None = "pane-a"
    metadata: dict | None = None
    updated_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class FakeRegistryRepo:
    def get(self, agent_id: str):
        return next((agent for agent in self.list_agents() if agent.agent_id == agent_id), None)

    def list_agents(self):
        return [
            FakeAgent(
                agent_id="agent-a",
                tenant_id="tenant-a",
                label="Agent A",
                vendor="codex",
                role="worker",
                updated_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
            )
        ]


class FakeTasksRepo:
    def list(self):
        return [
            SimpleNamespace(agent="agent-a", status="working", updated_at=datetime(2026, 6, 28, tzinfo=timezone.utc)),
            SimpleNamespace(agent="agent-a", status="done", updated_at=datetime(2026, 6, 28, tzinfo=timezone.utc)),
        ]


class BrokenTasksRepo:
    def list(self, *args, **kwargs):
        raise RuntimeError("tasks offline")


class FakeTraceRepo:
    def by_agent(self, agent_id: str):
        return [
            SimpleNamespace(
                agent_id=agent_id,
                tenant_id="tenant-a",
                project_id="project-a",
                token_burn=25,
                seat_seconds=12,
                occurred_at=datetime(2026, 6, 28, tzinfo=timezone.utc),
            )
        ]

    def burn_by_agent_runtime(self):
        return [{"agent_id": "agent-a", "runtime_id": "runtime-a", "token_burn": 25, "seat_seconds": 12, "event_count": 2}]


class FakeFinopsRepo:
    def list_projects(self):
        return [("tenant-a", "project-a")]

    def rollup_by_dimension(self, tenant_id: str, project_id: str, dimension: str):
        assert (tenant_id, project_id, dimension) == ("tenant-a", "project-a", "agent_id")
        return [
            SimpleNamespace(
                key="agent-a",
                total_cost_usd=Decimal("1.25"),
                token_cost_usd=Decimal("1.00"),
                seat_cost_usd=Decimal("0.25"),
            )
        ]


class FakeProjectsRepo:
    def list(self, tenant_id: str | None = None):
        projects = [
            SimpleNamespace(project_id="project-a", tenant_id="tenant-a"),
            SimpleNamespace(project_id="project-b", tenant_id="tenant-b"),
        ]
        if tenant_id is not None:
            projects = [project for project in projects if project.tenant_id == tenant_id]
        return projects

    def get(self, project_id: str):
        if project_id == "project-a":
            return SimpleNamespace(project_id=project_id, tenant_id="tenant-a")
        if project_id == "project-b":
            return SimpleNamespace(project_id=project_id, tenant_id="tenant-b")
        return None


class FakeTopologyRepo:
    def get_topology(self, squad_id: str):
        if squad_id == "project-a":
            return {
                "nodes": [
                    {"id": "tl", "role": "orchestrator"},
                    {"id": "agent-a", "role": "worker"},
                    {"id": "agent-b", "role": "worker"},
                ],
                "edges": [
                    {
                        "source": "tl",
                        "target": "agent-a",
                        "status": "ok",
                        "request_count": 10,
                        "error_count": 1,
                    },
                    {"source": "agent-a", "target": "tl", "status": "degraded"},
                    {"source": "agent-a", "target": "agent-b", "status": "disabled"},
                ],
            }
        if squad_id == "project-b":
            return {
                "nodes": [{"id": "other", "role": "worker"}],
                "edges": [{"source": "other", "target": "other", "status": "ok"}],
            }
        return None


def _client() -> TestClient:
    state = SimpleNamespace(
        registry_repo=FakeRegistryRepo(),
        tasks_repo=FakeTasksRepo(),
        trace_repo=FakeTraceRepo(),
        finops_repo=FakeFinopsRepo(),
        projects_repo=FakeProjectsRepo(),
        topology_repo=FakeTopologyRepo(),
    )
    app = FastAPI()

    @app.get("/example", tags=["example"])
    def example():
        return {"ok": True}

    app.include_router(build_dashboards_router(lambda: state, routes=lambda: list(app.routes), prefix="/dashboards"))
    return TestClient(app)


def test_agent_dashboards_snapshot_is_typed_and_aggregated() -> None:
    response = _client().get("/dashboards/agents")

    assert response.status_code == 200
    body = response.json()
    assert body["health"] == "ok"
    assert body["total_agents"] == 1
    assert body["active_tasks"] == 1
    assert body["total_token_burn"] == 25
    assert body["agents"][0]["agent_id"] == "agent-a"
    assert body["agents"][0]["total_cost_usd"] == "1.25"


def test_route_dashboards_snapshot_lists_registered_routes() -> None:
    app = FastAPI()

    @app.get("/example", tags=["example"])
    def example():
        return {"ok": True}

    snapshot = build_route_dashboards_snapshot(list(app.routes))

    paths = {route.path for route in snapshot.routes}
    assert "/example" in paths


def test_route_dashboards_filters_agent_routes_by_squad_agents_status_and_scope() -> None:
    state = SimpleNamespace(projects_repo=FakeProjectsRepo(), topology_repo=FakeTopologyRepo())

    snapshot = build_route_dashboards_snapshot(
        [],
        state=state,
        squad="project-a",
        source_agent="agent-a",
        target_agent="agent-b",
        status="unavailable",
        tenant_id="tenant-a",
        project_id="project-a",
    )

    assert snapshot.health == "ok"
    assert snapshot.total_routes == 1
    route = snapshot.routes[0]
    assert route.squad_id == "project-a"
    assert route.source_agent == "agent-a"
    assert route.target_agent == "agent-b"
    assert route.status == "unavailable"
    assert route.tenant_id == "tenant-a"
    assert route.project_id == "project-a"


def test_route_dashboards_filters_by_project_scope_without_squad_param() -> None:
    state = SimpleNamespace(projects_repo=FakeProjectsRepo(), topology_repo=FakeTopologyRepo())

    snapshot = build_route_dashboards_snapshot([], state=state, tenant_id="tenant-a", project_id="project-a")

    assert snapshot.total_routes == 3
    assert {route.squad_id for route in snapshot.routes} == {"project-a"}
    assert {route.tenant_id for route in snapshot.routes} == {"tenant-a"}


def test_route_dashboards_rejects_cross_tenant_project_scope() -> None:
    state = SimpleNamespace(projects_repo=FakeProjectsRepo(), topology_repo=FakeTopologyRepo())

    with pytest.raises(DashboardScopeViolationError):
        build_route_dashboards_snapshot([], state=state, tenant_id="tenant-b", project_id="project-a")


def test_single_agent_dashboard_enforces_tenant_and_project_scope() -> None:
    state = SimpleNamespace(
        registry_repo=FakeRegistryRepo(),
        tasks_repo=FakeTasksRepo(),
        trace_repo=FakeTraceRepo(),
        finops_repo=FakeFinopsRepo(),
        projects_repo=FakeProjectsRepo(),
    )

    detail = build_agent_dashboard_detail(
        state,
        "agent-a",
        tenant_id="tenant-a",
        project_id="project-a",
    )

    assert detail.health == "degraded"
    assert detail.agent.agent_id == "agent-a"
    assert detail.agent.token_burn == 25
    assert detail.agent.total_cost_usd == Decimal("1.25")
    assert detail.source_issues == ["tasks source lacks project_id for some agent tasks; omitted unscoped task rows"]


def test_single_agent_dashboard_rejects_cross_tenant_scope() -> None:
    state = SimpleNamespace(registry_repo=FakeRegistryRepo(), projects_repo=FakeProjectsRepo())

    response = _client().get("/dashboards/agents/agent-a", params={"tenant_id": "tenant-b"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "scope_violation"


def test_single_agent_dashboard_degrades_when_optional_source_fails() -> None:
    state = SimpleNamespace(
        registry_repo=FakeRegistryRepo(),
        tasks_repo=BrokenTasksRepo(),
        trace_repo=FakeTraceRepo(),
        finops_repo=FakeFinopsRepo(),
        projects_repo=FakeProjectsRepo(),
    )

    detail = build_agent_dashboard_detail(state, "agent-a", tenant_id="tenant-a")

    assert detail.health == "degraded"
    assert detail.agent.task_count == 0
    assert any("tasks_repo.list failed" in issue for issue in detail.source_issues)

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _use_local_terminal_adapter(monkeypatch):
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/aop-control-plane-test-no-herdr.sock")


def test_cors_allows_frontend_origin(api_client):
    origin = "http://127.0.0.1:13000"

    get_response = api_client.get("/agents", headers={"Origin": origin})
    assert get_response.status_code == 200
    assert get_response.headers["access-control-allow-origin"] == origin

    preflight = api_client.options(
        "/agents",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code in {200, 204}
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "GET" in preflight.headers["access-control-allow-methods"]


def test_health_ready_and_metrics(api_client):
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["coupling"]["status"] in {"connected", "degraded", "disconnected"}
    assert "last_error" in health.json()["coupling"]
    assert health.json()["coupling"]["message_bus_status"] == "degraded"

    ready = api_client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"postgres": True, "redis": True}
    assert ready.json()["coupling"] == health.json()["coupling"]

    metrics = api_client.get("/metrics")
    assert metrics.status_code == 200
    assert "aop_control_plane_up 1" in metrics.text
    assert "aop_finops_project_cost_usd" in metrics.text
    assert "aop_trace_token_burn_total" in metrics.text


def test_tasks_dispatch_socket_and_terminal_modes(api_client):
    socket_response = api_client.post(
        "/tasks",
        json={
            "task_id": "task-socket",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "issue_id": "issue-a",
            "assignee_runtime": "runtime-socket",
            "prompt": "run socket task",
            "operation_mode": "socket",
        },
    )
    assert socket_response.status_code == 200
    assert socket_response.json()["operation_mode"] == "socket"
    assert socket_response.json()["events"][-1]["status"] == "failed"
    assert "socket runtime unavailable" in socket_response.json()["events"][-1]["message"]

    terminal_response = api_client.post(
        "/tasks",
        json={
            "task_id": "task-terminal",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "issue_id": "issue-a",
            "assignee_runtime": "runtime-terminal",
            "prompt": "run terminal task",
            "operation_mode": "terminal",
        },
    )
    assert terminal_response.status_code == 200
    assert terminal_response.json()["operation_mode"] == "terminal"
    assert terminal_response.json()["events"][-1]["status"] == "failed"
    assert "terminal runtime unavailable" in terminal_response.json()["events"][-1]["message"]


def test_issues_crud_and_dispatch(api_client):
    created = api_client.post(
        "/issues",
        json={
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "title": "Issue API smoke",
            "description": "Dispatch from tracker",
            "priority": "high",
            "assignee_runtime": "runtime-issue",
            "operation_mode": "socket",
        },
    )
    assert created.status_code == 201
    issue = created.json()
    assert issue["status"] == "backlog"

    listed = api_client.get("/issues", params={"tenant_id": "tenant-a", "project_id": "project-a"})
    assert listed.status_code == 200
    assert listed.json()[0]["issue_id"] == issue["issue_id"]

    moved = api_client.patch(f"/issues/{issue['issue_id']}", json={"status": "in_progress"})
    assert moved.status_code == 200
    assert moved.json()["status"] == "in_progress"

    dispatched = api_client.post(f"/issues/{issue['issue_id']}/dispatch", json={"operation_mode": "terminal"})
    assert dispatched.status_code == 200
    assert dispatched.json()["events"][-1]["status"] == "failed"
    assert dispatched.json()["issue"]["status"] == "blocked"


def test_agents_degrade_without_registry_targets_and_seats_are_config_backed(api_client):
    created = api_client.post(
        "/agents",
        json={
            "tenant_id": "tenant-a",
            "label": "Codex Worker",
            "vendor": "codex",
            "role": "worker",
            "workspace_id": "workspace-main",
            "pane_id": "w1:p1",
            "stable_key": "tenant-a/codex-worker",
        },
    )
    assert created.status_code == 503
    assert created.json()["detail"]["code"] == "registry_propagation_unavailable"

    listed = api_client.get("/agents")
    assert listed.status_code == 200
    assert listed.json()[0]["pane_id"] == "w1:p1"

    seats = api_client.get("/seats")
    assert seats.status_code == 200
    assert seats.json()["seats"] == []


def test_topology_save_and_effective_acl(api_client):
    response = api_client.post(
        "/squads/squad-a/topology",
        json={
            "nodes": [
                {"id": "tl", "role": "orchestrator"},
                {"id": "worker", "role": "worker"},
            ],
            "edges": [
                {"source": "tl", "target": "worker"},
                {"source": "worker", "target": "tl"},
            ],
        },
    )
    assert response.status_code == 200
    effective = response.json()["effective_topology"]
    assert effective["default_policy"] == "deny"
    assert any(role["agents"] == ["tl"] and role["can_dispatch_tasks"] for role in effective["roles"])

    stored = api_client.get("/squads/squad-a/topology")
    assert stored.status_code == 200
    assert stored.json()["stored"]["nodes"][0]["id"] == "tl"


def test_finops_rollup_and_tracing_filters(api_client):
    token = api_client.post(
        "/finops/costs/token",
        json={
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "issue_id": "issue-a",
            "agent_id": "agent-a",
            "runtime_id": "runtime-a",
            "input_tokens": 10,
            "output_tokens": 10,
            "input_token_price_usd": "0.01",
            "output_token_price_usd": "0.02",
            "model": "api-model",
            "trace_id": "trace-a",
        },
    )
    assert token.status_code == 200
    assert token.json()["cost_usd"] == "0.30000000"

    seat = api_client.post(
        "/finops/costs/seat",
        json={
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "issue_id": "issue-a",
            "agent_id": "agent-a",
            "runtime_id": "runtime-a",
            "seat_id": "seat-a",
            "vendor": "codex",
            "used_seconds": 1800,
            "period_seconds": 3600,
            "period_cost_usd": "10.00",
            "trace_id": "trace-a",
        },
    )
    assert seat.status_code == 200

    rollup = api_client.get("/finops/projects/tenant-a/project-a/rollup")
    assert rollup.status_code == 200
    assert rollup.json()["record_count"] == 2
    assert rollup.json()["total_cost_usd"] == "5.30000000"

    trace_event = api_client.post(
        "/tracing/events",
        json={
            "trace_id": "trace-a",
            "layer": "l1_execution",
            "signal_type": "burn",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "issue_id": "issue-a",
            "agent_id": "agent-a",
            "runtime_id": "runtime-a",
            "message": "burn sample",
            "token_burn": 20,
            "seat_seconds": 30,
        },
    )
    assert trace_event.status_code == 200

    agent_trace = api_client.get("/tracing/agents/agent-a")
    runtime_trace = api_client.get("/tracing/runtimes/runtime-a")
    assert agent_trace.status_code == 200
    assert runtime_trace.status_code == 200
    assert agent_trace.json()[0]["trace_id"] == "trace-a"
    assert runtime_trace.json()[0]["runtime_id"] == "runtime-a"

    with api_client.websocket_connect("/ws/tracing/agents/agent-a") as websocket:
        websocket_events = websocket.receive_json()
    assert websocket_events[0]["trace_id"] == "trace-a"
    assert websocket_events[0]["agent_id"] == "agent-a"

    artifact = api_client.post(
        "/tracing/artifacts",
        json={
            "trace_id": "trace-a",
            "artifact_uri": "file:///tmp/trace-a.pty",
            "runtime_id": "runtime-a",
            "agent_id": "agent-a",
        },
    )
    assert artifact.status_code == 200
    assert artifact.json()["artifact_uri"] == "file:///tmp/trace-a.pty"

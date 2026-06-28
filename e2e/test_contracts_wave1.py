"""Wave 1 contract and UI smoke tests for the AOP surface.

These tests target a running local deployment. They intentionally skip when an
external service is absent, but they assert response contracts whenever an
endpoint answers.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

httpx = pytest.importorskip("httpx", reason="httpx is required for AOP E2E contract tests")

API_URL = os.environ.get("AOP_E2E_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
WEB_URL = os.environ.get("AOP_E2E_WEB_URL", "http://127.0.0.1:13000").rstrip("/")
TIMEOUT = httpx.Timeout(10.0, connect=2.0)


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    client = httpx.Client(base_url=API_URL, timeout=TIMEOUT)
    try:
        response = client.get("/health")
    except httpx.HTTPError as exc:
        client.close()
        pytest.skip(f"AOP API unavailable at {API_URL}: {exc}")
    if response.status_code >= 500:
        client.close()
        pytest.skip(f"AOP API not ready at {API_URL}: HTTP {response.status_code} {response.text[:200]}")
    yield client
    client.close()


@pytest.fixture(scope="session")
def web() -> httpx.Client:
    client = httpx.Client(base_url=WEB_URL, timeout=TIMEOUT)
    try:
        response = client.get("/")
    except httpx.HTTPError as exc:
        client.close()
        pytest.skip(f"AOP web unavailable at {WEB_URL}: {exc}")
    if response.status_code >= 500:
        client.close()
        pytest.skip(f"AOP web not ready at {WEB_URL}: HTTP {response.status_code} {response.text[:200]}")
    yield client
    client.close()


def _run_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _json(response: httpx.Response) -> dict | list:
    try:
        return response.json()
    except ValueError as exc:
        pytest.fail(f"{response.request.method} {response.request.url.path} did not return JSON: {exc}")


def _skip_runtime_unavailable(response: httpx.Response, label: str) -> None:
    if response.status_code in {500, 502, 503, 504}:
        pytest.skip(f"{label} runtime dependency unavailable: HTTP {response.status_code} {response.text[:300]}")


def test_health_ready_and_metrics_contract(api: httpx.Client) -> None:
    health = api.get("/health")
    assert health.status_code == 200
    health_data = _json(health)
    assert health_data["status"] == "ok"

    ready = api.get("/health/ready")
    if ready.status_code == 503:
        pytest.skip(f"readiness dependencies unavailable: {ready.text[:300]}")
    assert ready.status_code == 200
    ready_data = _json(ready)
    assert ready_data["status"] == "ready"
    assert isinstance(ready_data.get("checks"), dict)

    metrics = api.get("/metrics")
    assert metrics.status_code == 200
    assert "aop_control_plane_up 1" in metrics.text


def test_projects_contract_crud(api: httpx.Client) -> None:
    run_id = _run_id("qa-project")
    project_id = f"project-{run_id}"
    tenant_id = f"tenant-{run_id}"

    created = api.post(
        "/projects",
        json={
            "project_id": project_id,
            "tenant_id": tenant_id,
            "name": "QA E2E project",
            "description": "Wave 1 contract test",
            "metadata": {"source": "qa-e2e"},
        },
    )
    _skip_runtime_unavailable(created, "projects")
    assert created.status_code == 201
    project = _json(created)
    assert project["project_id"] == project_id
    assert project["tenant_id"] == tenant_id
    assert project["status"] == "active"

    listed = api.get("/projects", params={"tenant_id": tenant_id})
    assert listed.status_code == 200
    assert any(item["project_id"] == project_id for item in _json(listed))

    patched = api.patch(f"/projects/{project_id}", json={"status": "paused"})
    assert patched.status_code == 200
    assert _json(patched)["status"] == "paused"

    deleted = api.delete(f"/projects/{project_id}")
    assert deleted.status_code == 204


def test_seats_and_sessions_contract(api: httpx.Client, tmp_path) -> None:
    run_id = _run_id("qa-seat")
    seat_id = f"seat-{run_id}"
    tenant_id = f"tenant-{run_id}"
    home_dir = tmp_path / seat_id
    config_dir = home_dir / ".codex"

    initial = api.get("/seats")
    _skip_runtime_unavailable(initial, "seats")
    assert initial.status_code == 200
    assert isinstance(_json(initial).get("seats"), list)

    created = api.post(
        "/seats",
        json={
            "seat_id": seat_id,
            "tenant_id": tenant_id,
            "vendor": "codex",
            "home_dir": str(home_dir),
            "config_dir": str(config_dir),
            "display_name": "QA E2E Codex seat",
        },
    )
    assert created.status_code == 201
    seat = _json(created)["seat"]
    assert seat["available"] is True
    assert seat["leased"] is False
    assert seat["ref_count"] == 0

    login = api.post("/sessions/device-login", json={"seat_id": seat_id})
    if login.status_code == 202:
        session = _json(login)["session"]
        assert session["seat_id"] == seat_id
        assert session["status"] == "pending"
        status = api.get(f"/sessions/{session['session_id']}/status")
        assert status.status_code == 200
        assert _json(status)["session"]["session_id"] == session["session_id"]
    elif login.status_code == 503:
        detail = _json(login)["detail"]
        assert detail["code"] == "device_login_degraded"
        assert detail["session"]["seat_id"] == seat_id
        assert detail["session"]["status"] == "degraded"
    else:
        pytest.fail(f"unexpected device-login status {login.status_code}: {login.text}")

    sessions = api.get("/sessions", params={"seat_id": seat_id})
    assert sessions.status_code == 200
    assert isinstance(_json(sessions).get("sessions"), list)

    removed = api.delete(f"/seats/{seat_id}")
    assert removed.status_code == 200
    assert _json(removed)["removed"] is True


def test_tasks_contract_terminal_and_socket(api: httpx.Client) -> None:
    run_id = _run_id("qa-task")
    for mode in ("terminal", "socket"):
        response = api.post(
            "/tasks",
            json={
                "task_id": f"task-{mode}-{run_id}",
                "tenant_id": f"tenant-{run_id}",
                "project_id": f"project-{run_id}",
                "assignee_runtime": f"runtime-{mode}-{run_id}",
                "prompt": f"QA E2E {mode} task",
                "operation_mode": mode,
                "seat_seconds": 1,
            },
        )
        _skip_runtime_unavailable(response, f"{mode} task")
        assert response.status_code == 200
        data = _json(response)
        assert data["task_id"] == f"task-{mode}-{run_id}"
        assert data["operation_mode"] == mode
        assert isinstance(data["events"], list)
        assert data["events"], f"{mode} task returned no lifecycle events"
        assert all("status" in event for event in data["events"])


def test_topology_contract(api: httpx.Client) -> None:
    squad_id = _run_id("qa-squad")
    tl = f"agent-tl-{squad_id}"
    worker = f"agent-worker-{squad_id}"
    response = api.post(
        f"/squads/{squad_id}/topology",
        json={
            "nodes": [{"id": tl, "role": "orchestrator"}, {"id": worker, "role": "worker"}],
            "edges": [{"source": tl, "target": worker}, {"source": worker, "target": tl}],
        },
    )
    _skip_runtime_unavailable(response, "topology")
    assert response.status_code == 200
    effective = _json(response)["effective_topology"]
    assert effective["default_policy"] == "deny"
    assert isinstance(effective["roles"], list)

    stored = api.get(f"/squads/{squad_id}/topology")
    assert stored.status_code == 200
    assert _json(stored)["stored"]["nodes"][0]["id"] == tl


def test_finops_contract(api: httpx.Client) -> None:
    run_id = _run_id("qa-finops")
    tenant_id = f"tenant-{run_id}"
    project_id = f"project-{run_id}"
    issue_id = f"issue-{run_id}"
    trace_id = f"trace-{run_id}"

    token_cost = api.post(
        "/finops/costs/token",
        json={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "issue_id": issue_id,
            "agent_id": f"agent-{run_id}",
            "runtime_id": f"runtime-{run_id}",
            "input_tokens": 100,
            "output_tokens": 25,
            "input_token_price_usd": "0.000001",
            "output_token_price_usd": "0.000002",
            "model": "qa-e2e",
            "trace_id": trace_id,
        },
    )
    _skip_runtime_unavailable(token_cost, "finops token")
    assert token_cost.status_code == 200
    assert _json(token_cost)["engine"] == "token"

    seat_cost = api.post(
        "/finops/costs/seat",
        json={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "issue_id": issue_id,
            "agent_id": f"agent-{run_id}",
            "runtime_id": f"runtime-{run_id}",
            "seat_id": f"seat-{run_id}",
            "vendor": "codex",
            "used_seconds": 30,
            "period_seconds": 3600,
            "period_cost_usd": "12.00",
            "trace_id": trace_id,
        },
    )
    assert seat_cost.status_code == 200
    assert _json(seat_cost)["engine"] == "seat"

    rollup = api.get(f"/finops/projects/{tenant_id}/{project_id}/rollup")
    assert rollup.status_code == 200
    data = _json(rollup)
    assert data["tenant_id"] == tenant_id
    assert data["project_id"] == project_id
    assert int(data["record_count"]) >= 2


def test_tracing_contract(api: httpx.Client) -> None:
    run_id = _run_id("qa-trace")
    trace_id = f"trace-{run_id}"
    agent_id = f"agent-{run_id}"
    runtime_id = f"runtime-{run_id}"
    posted = api.post(
        "/tracing/events",
        json={
            "trace_id": trace_id,
            "layer": "l1_execution",
            "signal_type": "burn",
            "tenant_id": f"tenant-{run_id}",
            "project_id": f"project-{run_id}",
            "issue_id": f"issue-{run_id}",
            "agent_id": agent_id,
            "runtime_id": runtime_id,
            "message": "QA E2E trace event",
            "token_burn": 9,
            "seat_seconds": 3,
        },
    )
    _skip_runtime_unavailable(posted, "tracing")
    assert posted.status_code == 200
    assert _json(posted)["trace_id"] == trace_id

    by_agent = api.get(f"/tracing/agents/{agent_id}")
    assert by_agent.status_code == 200
    assert any(event["trace_id"] == trace_id for event in _json(by_agent))

    by_runtime = api.get(f"/tracing/runtimes/{runtime_id}")
    assert by_runtime.status_code == 200
    assert any(event["trace_id"] == trace_id for event in _json(by_runtime))


@pytest.mark.parametrize(
    "route",
    [
        "/",
        "/projects",
        "/issues",
        "/seats",
        "/sessions",
        "/finops",
        "/observability",
        "/live",
        "/settings",
        "/inbox",
        "/my-issues",
        "/squad-builder",
    ],
)
def test_next_ui_routes_smoke(web: httpx.Client, route: str) -> None:
    try:
        response = web.get(route)
    except httpx.HTTPError as exc:
        pytest.skip(f"Next route {route} unavailable at {WEB_URL}: {exc}")
    if response.status_code in {502, 503, 504}:
        pytest.skip(f"Next route {route} dependency unavailable: HTTP {response.status_code}")
    assert response.status_code == 200
    assert "<html" in response.text.lower()
    forbidden = ("next.js server error", "application error", "runtime error", "unhandled runtime error")
    assert not any(marker in response.text.lower() for marker in forbidden)

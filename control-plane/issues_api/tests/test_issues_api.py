from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.main import create_app
from app.settings import Settings
from issues_api import IssuePriority, IssueRepository, IssueStatus


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    port = os.environ.get("POSTGRES_PORT") or values.get("POSTGRES_PORT") or "5432"
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{port}/{values['POSTGRES_DB']}"
    )


def test_issue_repository_crud_persists(issues_conn):
    repo = IssueRepository(issues_conn)

    created = repo.create(
        tenant_id="tenant-a",
        project_id="project-a",
        title="Wire issue tracker",
        description="Create the board",
        priority=IssuePriority.HIGH,
        assignee_runtime="runtime-a",
        operation_mode="socket",
        metadata={"label": "F2"},
    )

    assert created.issue_id.startswith("issue-")
    assert created.status == IssueStatus.BACKLOG
    assert created.priority == IssuePriority.HIGH
    assert repo.get(created.issue_id) == created

    updated = repo.update(
        created.issue_id,
        status=IssueStatus.IN_PROGRESS,
        priority=IssuePriority.CRITICAL,
        metadata={"label": "F2", "dispatch": "started"},
    )

    assert updated is not None
    assert updated.status == IssueStatus.IN_PROGRESS
    assert updated.priority == IssuePriority.CRITICAL
    assert updated.metadata["dispatch"] == "started"
    assert repo.list(status=IssueStatus.IN_PROGRESS)[0].issue_id == created.issue_id

    deleted = repo.delete(created.issue_id)
    assert deleted is not None
    assert deleted.deleted_at is not None
    assert repo.get(created.issue_id) is None


def test_issue_endpoints_and_dispatch(monkeypatch):
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"issues_api_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"issues_api_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"issues_api_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"issues_api_projects_test_{uuid4().hex}",
        "AOP_ISSUES_SCHEMA": f"issues_api_issues_test_{uuid4().hex}",
    }
    for key, value in schemas.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/aop-issues-test-no-herdr.sock")

    settings = Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        host="127.0.0.1",
        port=8090,
    )

    try:
        with TestClient(create_app(settings)) as client:
            created = client.post(
                "/issues",
                json={
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "title": "Build issue tracker",
                    "description": "Implement board and dispatch",
                    "priority": "high",
                    "assignee_runtime": "runtime-a",
                    "operation_mode": "socket",
                },
            )
            assert created.status_code == 201
            issue = created.json()
            assert issue["status"] == "backlog"
            assert issue["operation_mode"] == "socket"

            listed = client.get("/issues", params={"project_id": "project-a", "status": "backlog"})
            assert listed.status_code == 200
            assert [item["issue_id"] for item in listed.json()] == [issue["issue_id"]]

            patched = client.patch(
                f"/issues/{issue['issue_id']}",
                json={"status": "todo", "priority": "critical"},
            )
            assert patched.status_code == 200
            assert patched.json()["status"] == "todo"
            assert patched.json()["priority"] == "critical"

            dispatched = client.post(
                f"/issues/{issue['issue_id']}/dispatch",
                json={"operation_mode": "terminal", "assignee_runtime": "runtime-terminal"},
            )
            assert dispatched.status_code == 200
            body = dispatched.json()
            assert body["operation_mode"] == "terminal"
            assert body["events"][-1]["status"] == "failed"
            assert body["issue"]["status"] == "blocked"
            assert body["issue"]["metadata"]["last_task_id"] == f"task-{issue['issue_id']}"

            deleted = client.delete(f"/issues/{issue['issue_id']}")
            assert deleted.status_code == 204
            assert client.get(f"/issues/{issue['issue_id']}").status_code == 404
    finally:
        with psycopg.connect(database_url) as cleanup:
            with cleanup.cursor() as cur:
                for schema_name in schemas.values():
                    cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))


def test_issues_my_endpoint(monkeypatch):
    """Test the GET /issues/my endpoint with all scope variations."""
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"issues_my_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"issues_my_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"issues_my_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"issues_my_projects_test_{uuid4().hex}",
        "AOP_ISSUES_SCHEMA": f"issues_my_issues_test_{uuid4().hex}",
    }
    for key, value in schemas.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/aop-issues-my-test-no-herdr.sock")

    settings = Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        host="127.0.0.1",
        port=8090,
    )

    try:
        with TestClient(create_app(settings)) as client:
            # Create issue assigned to agent-alpha
            created_assigned = client.post(
                "/issues",
                headers={"X-Agent-Id": "agent-alpha"},
                json={
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "title": "Assigned to alpha and stamped by alpha",
                    "assignee_runtime": "agent-alpha",
                    "metadata": {},
                },
            )
            assert created_assigned.status_code == 201
            assert created_assigned.json()["metadata"]["created_by"] == "agent-alpha"

            # Create issue created by agent-alpha (in metadata)
            created_by = client.post(
                "/issues",
                json={
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "title": "Created by alpha",
                    "assignee_runtime": "agent-beta",
                    "metadata": {"created_by": "agent-alpha"},
                },
            )
            assert created_by.status_code == 201

            # Create issue assigned to agent-alpha-sub1 (for my-agents scope)
            created_sub = client.post(
                "/issues",
                json={
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "title": "Assigned to sub-agent",
                    "assignee_runtime": "agent-alpha-sub1",
                    "metadata": {},
                },
            )
            assert created_sub.status_code == 201

            # Create unrelated issue
            client.post(
                "/issues",
                json={
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "title": "Unrelated issue",
                    "assignee_runtime": "agent-gamma",
                    "metadata": {"created_by": "agent-gamma"},
                },
            )

            # 1. No agent_id → 400
            resp = client.get("/issues/my")
            assert resp.status_code == 400

            # 2. scope=all → returns assigned + created by agent-alpha
            resp = client.get("/issues/my", params={"agent_id": "agent-alpha", "scope": "all"})
            assert resp.status_code == 200
            titles = {item["title"] for item in resp.json()}
            assert "Assigned to alpha and stamped by alpha" in titles
            assert "Created by alpha" in titles
            assert "Unrelated issue" not in titles

            # 2b. /api alias used by the frontend returns the same real data.
            resp = client.get("/api/issues/my", params={"agent_id": "agent-alpha", "scope": "all"})
            assert resp.status_code == 200
            titles = {item["title"] for item in resp.json()}
            assert "Assigned to alpha and stamped by alpha" in titles
            assert "Created by alpha" in titles

            # 3. scope=assigned → only assigned to agent-alpha
            resp = client.get("/issues/my", params={"agent_id": "agent-alpha", "scope": "assigned"})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["title"] == "Assigned to alpha and stamped by alpha"

            # 4. scope=created → only created by agent-alpha
            resp = client.get("/issues/my", params={"agent_id": "agent-alpha", "scope": "created"})
            assert resp.status_code == 200
            data = resp.json()
            titles = {item["title"] for item in data}
            assert titles == {"Assigned to alpha and stamped by alpha", "Created by alpha"}

            # 5. scope=my-agents → prefix match on agent-alpha
            resp = client.get("/issues/my", params={"agent_id": "agent-alpha", "scope": "my-agents"})
            assert resp.status_code == 200
            titles = {item["title"] for item in resp.json()}
            assert "Assigned to alpha and stamped by alpha" in titles
            assert "Assigned to sub-agent" in titles
            assert "Unrelated issue" not in titles

            # 6. X-Agent-Id header
            resp = client.get(
                "/issues/my",
                params={"scope": "assigned"},
                headers={"X-Agent-Id": "agent-alpha"},
            )
            assert resp.status_code == 200
            assert len(resp.json()) == 1
            assert resp.json()[0]["assignee_runtime"] == "agent-alpha"

            # 7. Verify each issue has required fields
            resp = client.get("/issues/my", params={"agent_id": "agent-alpha"})
            for item in resp.json():
                assert "issue_id" in item
                assert "title" in item
                assert "status" in item
                assert "priority" in item
                assert "assignee_runtime" in item
                assert "created_at" in item
                assert "project_id" in item
    finally:
        with psycopg.connect(database_url) as cleanup:
            with cleanup.cursor() as cur:
                for schema_name in schemas.values():
                    cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))

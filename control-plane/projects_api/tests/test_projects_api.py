from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.main import create_app
from app.settings import Settings
from projects_api import ProjectRepository, ProjectStatus


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:5432/{values['POSTGRES_DB']}"
    )


def test_project_repository_crud_persists(projects_conn):
    repo = ProjectRepository(projects_conn)

    created = repo.create(
        tenant_id="tenant-a",
        name="Control Plane",
        description="Backend project",
        metadata={"source": "test"},
    )

    assert created.project_id.startswith("project-")
    assert created.status == ProjectStatus.ACTIVE
    assert repo.get(created.project_id) == created
    assert repo.count() == 1

    updated = repo.update(
        created.project_id,
        name="Control Plane API",
        status=ProjectStatus.PAUSED,
        metadata={"priority": "high"},
    )

    assert updated is not None
    assert updated.name == "Control Plane API"
    assert updated.status == ProjectStatus.PAUSED
    assert updated.metadata == {"priority": "high"}

    deleted = repo.delete(created.project_id)
    assert deleted is not None
    assert deleted.deleted_at is not None
    assert repo.get(created.project_id) is None
    assert repo.list() == []


def test_projects_endpoints_crud_and_persistence(monkeypatch):
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"projects_api_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"projects_api_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"projects_api_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"projects_api_projects_test_{uuid4().hex}",
    }
    for key, value in schemas.items():
        monkeypatch.setenv(key, value)

    settings = Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        host="127.0.0.1",
        port=8090,
    )

    try:
        with TestClient(create_app(settings)) as client:
            created = client.post(
                "/projects",
                json={
                    "tenant_id": "tenant-a",
                    "name": "AOP Runtime",
                    "description": "Real Postgres project",
                    "metadata": {"owner": "ag-2"},
                },
            )
            assert created.status_code == 201
            project = created.json()
            assert project["project_id"].startswith("project-")
            assert project["tenant_id"] == "tenant-a"
            assert project["metadata"] == {"owner": "ag-2"}

            listed = client.get("/projects", params={"tenant_id": "tenant-a"})
            assert listed.status_code == 200
            assert [item["project_id"] for item in listed.json()] == [project["project_id"]]

            fetched = client.get(f"/projects/{project['project_id']}")
            assert fetched.status_code == 200
            assert fetched.json()["name"] == "AOP Runtime"

            patched = client.patch(
                f"/projects/{project['project_id']}",
                json={"name": "AOP Runtime API", "status": "paused", "metadata": {"stage": "wave-1"}},
            )
            assert patched.status_code == 200
            assert patched.json()["name"] == "AOP Runtime API"
            assert patched.json()["status"] == "paused"
            assert patched.json()["metadata"] == {"stage": "wave-1"}

            persisted = client.get(f"/projects/{project['project_id']}")
            assert persisted.status_code == 200
            assert persisted.json()["updated_at"] == patched.json()["updated_at"]

            deleted = client.delete(f"/projects/{project['project_id']}")
            assert deleted.status_code == 204
            assert client.get(f"/projects/{project['project_id']}").status_code == 404
            assert client.get("/projects").json() == []
    finally:
        with psycopg.connect(database_url) as cleanup:
            with cleanup.cursor() as cur:
                for schema_name in schemas.values():
                    cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))

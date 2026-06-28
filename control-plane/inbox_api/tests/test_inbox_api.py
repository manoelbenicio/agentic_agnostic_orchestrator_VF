from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.main import create_app
from app.settings import Settings
from inbox_api import InboxRepository, InboxEventType


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    postgres_port = os.environ.get("POSTGRES_PORT", "5432")
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{postgres_port}/{values['POSTGRES_DB']}"
    )


def test_inbox_repository_crud(inbox_conn):
    repo = InboxRepository(inbox_conn)

    # initially empty
    assert repo.list() == []
    assert repo.unread_count() == 0

    # create event
    created = repo.create(
        tenant_id="tenant-a",
        type=InboxEventType.TASK_COMPLETED,
        title="Task #42 completed",
        message="Build finished successfully.",
    )
    assert created.id.startswith("inbox-")
    assert created.type == InboxEventType.TASK_COMPLETED
    assert created.read is False
    assert created.archived is False

    # list returns it
    events = repo.list()
    assert len(events) == 1
    assert events[0].id == created.id

    # unread count
    assert repo.unread_count() == 1
    assert repo.unread_count(tenant_id="tenant-a") == 1
    assert repo.unread_count(tenant_id="tenant-b") == 0

    # mark read
    read_event = repo.mark_read(created.id)
    assert read_event is not None
    assert read_event.read is True
    assert repo.unread_count() == 0

    # filter by read
    assert len(repo.list(read=True)) == 1
    assert len(repo.list(read=False)) == 0

    # bulk archive
    count = repo.bulk_archive([created.id])
    assert count == 1
    assert repo.list(archived=False) == []
    assert len(repo.list(archived=True)) == 1


def test_inbox_endpoints_crud(monkeypatch):
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"inbox_api_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"inbox_api_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"inbox_api_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"inbox_api_projects_test_{uuid4().hex}",
        "AOP_ISSUES_SCHEMA": f"inbox_api_issues_test_{uuid4().hex}",
        "AOP_INBOX_SCHEMA": f"inbox_api_inbox_test_{uuid4().hex}",
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
            # GET /inbox — initially empty
            listed = client.get("/inbox")
            assert listed.status_code == 200
            assert listed.json() == []

            # GET /inbox/unread-count — initially zero
            unread = client.get("/inbox/unread-count")
            assert unread.status_code == 200
            assert unread.json()["count"] == 0

            # POST /inbox — create event
            created = client.post(
                "/inbox",
                json={
                    "tenant_id": "tenant-a",
                    "type": "task_completed",
                    "title": "Deployment done",
                    "message": "All agents deployed.",
                },
            )
            assert created.status_code == 201
            event = created.json()
            assert event["id"].startswith("inbox-")
            assert event["tenant_id"] == "tenant-a"
            assert event["type"] == "task_completed"
            assert event["read"] is False
            assert event["archived"] is False

            # GET /inbox — now has one event
            listed = client.get("/inbox")
            assert listed.status_code == 200
            assert len(listed.json()) == 1

            # GET /inbox/unread-count — now 1
            unread = client.get("/inbox/unread-count")
            assert unread.json()["count"] == 1

            # POST /inbox/{id}/read — mark as read
            marked = client.post(f"/inbox/{event['id']}/read")
            assert marked.status_code == 200
            assert marked.json()["read"] is True

            # unread count back to 0
            unread = client.get("/inbox/unread-count")
            assert unread.json()["count"] == 0

            # POST /inbox/bulk-archive
            archived = client.post(
                "/inbox/bulk-archive",
                json={"event_ids": [event["id"]]},
            )
            assert archived.status_code == 200
            assert archived.json()["archived_count"] == 1

            # GET /inbox — empty again (archived events not shown by default)
            listed = client.get("/inbox")
            assert listed.status_code == 200
            assert listed.json() == []

            # 404 on mark_read of non-existent
            assert client.post("/inbox/nonexistent/read").status_code == 404
    finally:
        with psycopg.connect(database_url) as cleanup:
            with cleanup.cursor() as cur:
                for schema_name in schemas.values():
                    cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))

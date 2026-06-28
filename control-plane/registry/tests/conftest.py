from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql

from registry.propagation import (
    CompositePropagationHook,
    RecordingPropagationHook,
)
from registry.repository import AgentRegistryRepository
from registry.schema import connect, init_schema
from registry.service import AgentRegistryService


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    user = values["POSTGRES_USER"]
    password = values["POSTGRES_PASSWORD"]
    db = values["POSTGRES_DB"]
    return f"postgresql://{user}:{password}@127.0.0.1:5432/{db}"


@pytest.fixture
def registry_conn():
    schema_name = f"registry_test_{uuid4().hex}"
    conn = connect(database_url=_database_url(), schema_name=schema_name)
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
        conn.commit()
        conn.close()


@pytest.fixture
def hooks():
    acl = RecordingPropagationHook("acl-test")
    allowlist = RecordingPropagationHook("allowlist-test")
    observability = RecordingPropagationHook("observability-test")
    scheduler = RecordingPropagationHook("scheduler-test")
    return (acl, allowlist, observability, scheduler)


@pytest.fixture
def service(registry_conn, hooks):
    return AgentRegistryService(
        repository=AgentRegistryRepository(registry_conn),
        propagation=CompositePropagationHook(hooks),
        enrolled_workspaces={"workspace-main"},
    )

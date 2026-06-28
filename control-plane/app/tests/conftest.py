from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.main import create_app
from app.settings import Settings


def _database_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    postgres_port = os.environ.get("POSTGRES_PORT") or values.get("POSTGRES_PORT") or "5432"
    return (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:{postgres_port}/{values['POSTGRES_DB']}"
    )


def _redis_url() -> str:
    env_path = Path(__file__).resolve().parents[3] / "deploy" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    redis_port = os.environ.get("REDIS_PORT") or values.get("REDIS_PORT") or "6379"
    redis_password = os.environ.get("REDIS_PASSWORD") or values.get("REDIS_PASSWORD") or ""
    if redis_password:
        return f"redis://:{redis_password}@127.0.0.1:{redis_port}/0"
    return f"redis://127.0.0.1:{redis_port}/0"


@pytest.fixture
def api_client(monkeypatch):
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"app_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"app_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"app_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"app_projects_test_{uuid4().hex}",
        "AOP_ISSUES_SCHEMA": f"app_issues_test_{uuid4().hex}",
        "AOP_SEATS_API_SCHEMA": f"app_seats_test_{uuid4().hex}",
        "AOP_SESSIONS_API_SCHEMA": f"app_sessions_test_{uuid4().hex}",
        "AOP_PROVISIONING_SCHEMA": f"app_provisioning_test_{uuid4().hex}",
    }
    for key, value in schemas.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AOP_SEATS_FILE", raising=False)
    monkeypatch.delenv("AOP_SEATS_JSON", raising=False)

    settings = Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL") or _redis_url(),
        host="127.0.0.1",
        port=8090,
    )
    with TestClient(create_app(settings)) as client:
        yield client

    conn = psycopg.connect(database_url)
    try:
        with conn.cursor() as cur:
            for schema_name in schemas.values():
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
        conn.commit()
    finally:
        conn.close()

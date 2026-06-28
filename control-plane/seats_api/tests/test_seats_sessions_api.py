from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
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


def _client(monkeypatch, *, device_login_commands: dict[str, str] | None = None):
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"ag4_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"ag4_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"ag4_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"ag4_projects_test_{uuid4().hex}",
        "AOP_SEATS_API_SCHEMA": f"ag4_seats_test_{uuid4().hex}",
        "AOP_SESSIONS_API_SCHEMA": f"ag4_sessions_test_{uuid4().hex}",
    }
    for key, value in schemas.items():
        monkeypatch.setenv(key, value)

    settings = Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL") or _redis_url(),
        host="127.0.0.1",
        port=8090,
        device_login_commands_json=json.dumps(device_login_commands or {}),
    )
    return database_url, schemas, TestClient(create_app(settings))


def _drop_schemas(database_url: str, schemas: dict[str, str]) -> None:
    with psycopg.connect(database_url) as cleanup:
        with cleanup.cursor() as cur:
            for schema_name in schemas.values():
                cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))


def test_seats_start_empty_and_crud_with_isolated_paths(monkeypatch, tmp_path):
    database_url, schemas, client = _client(monkeypatch)
    try:
        with client:
            assert client.get("/seats").json() == {"seats": []}

            outside_home = client.post(
                "/seats",
                json={
                    "seat_id": "seat-bad",
                    "tenant_id": "tenant-a",
                    "vendor": "codex",
                    "home_dir": str(tmp_path / "seat-bad"),
                    "config_dir": str(tmp_path / "other-config"),
                },
            )
            assert outside_home.status_code == 422

            home_dir = tmp_path / "seat-codex"
            created = client.post(
                "/seats",
                json={
                    "seat_id": "seat-codex",
                    "tenant_id": "tenant-a",
                    "vendor": "codex",
                    "home_dir": str(home_dir),
                    "config_dir": str(home_dir / ".codex"),
                    "display_name": "Codex seat",
                    "metadata": {"owner": "ag-4"},
                },
            )
            assert created.status_code == 201
            seat = created.json()["seat"]
            assert seat["available"] is True
            assert seat["leased"] is False
            assert seat["ref_count"] == 0

            patched = client.patch("/seats/seat-codex", json={"display_name": "Codex primary"})
            assert patched.status_code == 200
            assert patched.json()["seat"]["display_name"] == "Codex primary"

            listed = client.get("/seats", params={"vendor": "codex"})
            assert [item["seat_id"] for item in listed.json()["seats"]] == ["seat-codex"]

            removed = client.delete("/seats/seat-codex")
            assert removed.status_code == 200
            assert client.get("/seats").json() == {"seats": []}
    finally:
        _drop_schemas(database_url, schemas)


def test_device_login_uses_vendor_command_and_updates_session_status(monkeypatch, tmp_path):
    provider = tmp_path / "provider.py"
    provider.write_text(
        "import json, os\n"
        "assert os.environ['HOME'].endswith('seat-claude')\n"
        "assert os.environ['AOP_SEAT_CONFIG_DIR'].endswith('.claude')\n"
        "print(json.dumps({'verification_uri': 'https://login.example/device', 'user_code': 'ABCD-EFGH', 'device_code_ref': 'dev-1', 'expires_in': 600}))\n",
        encoding="utf-8",
    )
    database_url, schemas, client = _client(
        monkeypatch,
        device_login_commands={"claude": f"{sys.executable} {provider}"},
    )
    try:
        with client:
            home_dir = tmp_path / "seat-claude"
            assert client.post(
                "/seats",
                json={
                    "seat_id": "seat-claude",
                    "tenant_id": "tenant-a",
                    "vendor": "claude",
                    "home_dir": str(home_dir),
                    "config_dir": str(home_dir / ".claude"),
                },
            ).status_code == 201

            login = client.post("/sessions/device-login", json={"seat_id": "seat-claude"})
            assert login.status_code == 202
            session = login.json()["session"]
            assert session["vendor"] == "claude"
            assert session["status"] == "pending"
            assert session["verification_uri"] == "https://login.example/device"
            assert session["user_code"] == "ABCD-EFGH"
            assert (home_dir / ".claude").is_dir()

            seats = client.get("/seats").json()["seats"]
            assert seats[0]["leased"] is True
            assert seats[0]["available"] is False
            assert seats[0]["ref_count"] == 1

            status = client.get(f"/sessions/{session['session_id']}/status")
            assert status.status_code == 200
            assert status.json()["session"]["status"] == "pending"

            filtered = client.get("/sessions", params={"vendor": "claude"})
            assert [item["session_id"] for item in filtered.json()["sessions"]] == [session["session_id"]]
    finally:
        _drop_schemas(database_url, schemas)


def test_device_login_degrades_without_provider(monkeypatch, tmp_path):
    database_url, schemas, client = _client(monkeypatch)
    try:
        with client:
            home_dir = tmp_path / "seat-gemini"
            assert client.post(
                "/seats",
                json={
                    "seat_id": "seat-gemini",
                    "tenant_id": "tenant-a",
                    "vendor": "gemini",
                    "home_dir": str(home_dir),
                    "config_dir": str(home_dir / ".gemini"),
                },
            ).status_code == 201

            login = client.post("/sessions/device-login", json={"seat_id": "seat-gemini"})
            assert login.status_code == 503
            detail = login.json()["detail"]
            assert detail["code"] == "device_login_degraded"
            assert detail["session"]["status"] == "degraded"
            assert "not configured" in detail["session"]["status_reason"]
    finally:
        _drop_schemas(database_url, schemas)

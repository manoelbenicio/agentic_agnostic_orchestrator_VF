"""Tests for the settings API: repository CRUD and HTTP endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.main import create_app
from app.settings import Settings
from settings_api import SettingsRepository


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


def test_settings_repository_crud(settings_conn):
    repo = SettingsRepository(settings_conn)

    # Settings: initially empty
    assert repo.get_settings("tenant-a") == []

    # Upsert settings
    s1 = repo.upsert_setting(tenant_id="tenant-a", key="workspace_name", value="My Workspace")
    assert s1.key == "workspace_name"
    assert s1.value == "My Workspace"

    # Read back
    settings = repo.get_settings("tenant-a")
    assert len(settings) == 1
    assert settings[0].value == "My Workspace"

    # Update existing
    s2 = repo.upsert_setting(tenant_id="tenant-a", key="workspace_name", value="Renamed Workspace")
    assert s2.value == "Renamed Workspace"

    # Profile
    profile = repo.upsert_profile("tenant-a", {"display_name": "Admin", "email": "admin@test.com"})
    assert profile["display_name"] == "Admin"
    assert profile["email"] == "admin@test.com"

    profile_read = repo.get_profile("tenant-a")
    assert profile_read == profile

    # Integrations
    assert repo.list_integrations("tenant-a") == []
    intg = repo.create_integration(
        tenant_id="tenant-a",
        name="Slack",
        provider="slack",
        config={"webhook": "https://hooks.slack.com/test"},
    )
    assert intg.name == "Slack"
    assert intg.provider == "slack"
    integrations = repo.list_integrations("tenant-a")
    assert len(integrations) == 1

    # API Tokens
    assert repo.list_tokens("tenant-a") == []
    token = repo.create_token(tenant_id="tenant-a", name="CI Token", token_hash="hash123", prefix="abc")
    assert token.name == "CI Token"
    assert token.token_hash == "hash123"
    tokens = repo.list_tokens("tenant-a")
    assert len(tokens) == 1

    # Revoke token
    revoked = repo.revoke_token(token.token_id)
    assert revoked is not None
    assert revoked.revoked_at is not None
    assert repo.list_tokens("tenant-a") == []

    with settings_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name IN ('settings', 'api_tokens', 'integrations')
            ORDER BY table_name
            """
        )
        assert [row["table_name"] for row in cur.fetchall()] == ["api_tokens", "settings"]
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'api_tokens'
              AND column_name IN ('id', 'tenant_id', 'name', 'token_hash', 'created_at', 'expires_at', 'token_id')
            ORDER BY column_name
            """
        )
        assert [row["column_name"] for row in cur.fetchall()] == [
            "created_at",
            "expires_at",
            "id",
            "name",
            "tenant_id",
            "token_hash",
        ]


def test_settings_endpoints_crud(monkeypatch):
    database_url = _database_url()
    schemas = {
        "AOP_REGISTRY_SCHEMA": f"settings_api_registry_test_{uuid4().hex}",
        "AOP_FINOPS_SCHEMA": f"settings_api_finops_test_{uuid4().hex}",
        "AOP_TRACING_SCHEMA": f"settings_api_tracing_test_{uuid4().hex}",
        "AOP_PROJECTS_SCHEMA": f"settings_api_projects_test_{uuid4().hex}",
        "AOP_SETTINGS_SCHEMA": f"settings_api_settings_test_{uuid4().hex}",
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
            # GET /settings — initially empty
            res = client.get("/settings", params={"tenant_id": "tenant-a"})
            assert res.status_code == 200
            assert res.json()["settings"] == {}

            # PATCH /settings
            res = client.patch(
                "/settings",
                json={"tenant_id": "tenant-a", "settings": {"workspace_name": "AOP Lab", "theme": "dark"}},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["settings"]["workspace_name"] == "AOP Lab"
            assert data["settings"]["theme"] == "dark"

            # GET /settings/profile — initially empty
            res = client.get("/settings/profile", params={"tenant_id": "tenant-a"})
            assert res.status_code == 200
            assert res.json()["profile"] == {}

            # PATCH /settings/profile
            res = client.patch(
                "/settings/profile",
                json={"tenant_id": "tenant-a", "profile": {"display_name": "Admin", "email": "admin@aop.dev"}},
            )
            assert res.status_code == 200
            assert res.json()["profile"]["display_name"] == "Admin"

            # GET /settings/integrations — empty
            res = client.get("/settings/integrations", params={"tenant_id": "tenant-a"})
            assert res.status_code == 200
            assert res.json() == []

            # POST /settings/integrations
            res = client.post(
                "/settings/integrations",
                json={"tenant_id": "tenant-a", "name": "GitHub", "provider": "github", "config": {"org": "aop"}},
            )
            assert res.status_code == 201
            assert res.json()["name"] == "GitHub"

            # GET /settings/api-tokens — empty
            res = client.get("/settings/api-tokens", params={"tenant_id": "tenant-a"})
            assert res.status_code == 200
            assert res.json() == []

            # POST /settings/api-tokens
            res = client.post(
                "/settings/api-tokens",
                json={"tenant_id": "tenant-a", "name": "Deploy Key"},
            )
            assert res.status_code == 201
            token_data = res.json()
            assert token_data["name"] == "Deploy Key"
            assert "raw_token" in token_data
            token_id = token_data["token_id"]

            # Verify token listed
            res = client.get("/settings/api-tokens", params={"tenant_id": "tenant-a"})
            assert res.status_code == 200
            assert len(res.json()) == 1

            # DELETE /settings/api-tokens/{id}
            res = client.delete(f"/settings/api-tokens/{token_id}")
            assert res.status_code == 204

            # Verify token gone
            res = client.get("/settings/api-tokens", params={"tenant_id": "tenant-a"})
            assert res.status_code == 200
            assert res.json() == []

            # DELETE non-existent token
            res = client.delete("/settings/api-tokens/nonexistent")
            assert res.status_code == 404
    finally:
        with psycopg.connect(database_url) as cleanup:
            with cleanup.cursor() as cur:
                for schema_name in schemas.values():
                    cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))

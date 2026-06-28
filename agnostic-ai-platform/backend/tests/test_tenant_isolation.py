from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api_keys import APIKeyCreateRequest, api_key_manager
from app.auth import JWTAuthMiddleware, create_access_token
from app.tenant_isolation import (
    CrossTenantAccessError,
    TenantContext,
    TenantIsolationMiddleware,
    apply_tenant_filter,
    prevent_cross_tenant_access,
    tenant_query_filter,
)


def test_tenant_context_is_injected_from_jwt() -> None:
    app = FastAPI()
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(TenantIsolationMiddleware, enforce_rate_limits=False)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str | None]:
        context = request.state.tenant_context
        return {
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "auth_type": context.auth_type,
            "state_tenant_id": request.state.tenant_id,
        }

    token = create_access_token(user_id="user-1", role="admin", tenant_id="tenant-jwt")
    response = TestClient(app).get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "tenant-jwt",
        "project_id": None,
        "auth_type": "jwt",
        "state_tenant_id": "tenant-jwt",
    }


def test_tenant_context_is_injected_from_api_key_and_bypasses_jwt_middleware() -> None:
    response = api_key_manager.create_key(
        APIKeyCreateRequest(
            name="tenant key",
            tenant_id="tenant-key",
            project_id="project-1",
            rate_limit_rpm=60,
            rate_limit_tpm=1000,
        )
    )
    app = FastAPI()
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(TenantIsolationMiddleware, enforce_rate_limits=False)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str | None]:
        context = request.state.tenant_context
        return {
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "auth_type": context.auth_type,
            "role": request.state.role,
        }

    result = TestClient(app).get("/whoami", headers={"X-API-Key": response.api_key})

    assert result.status_code == 200
    assert result.json() == {
        "tenant_id": "tenant-key",
        "project_id": "project-1",
        "auth_type": "api_key",
        "role": "api_key",
    }


def test_cross_tenant_access_prevention_rejects_mismatched_tenant() -> None:
    app = FastAPI()
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(TenantIsolationMiddleware, enforce_rate_limits=False)

    @app.get("/tenants/{tenant_id}/resource")
    async def resource(request: Request, tenant_id: str) -> dict[str, str]:
        context = prevent_cross_tenant_access(request, tenant_id=tenant_id)
        return {"tenant_id": context.tenant_id}

    token = create_access_token(user_id="user-1", role="admin", tenant_id="tenant-a")
    client = TestClient(app)

    assert client.get("/tenants/tenant-a/resource", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    forbidden = client.get("/tenants/tenant-b/resource", headers={"Authorization": f"Bearer {token}"})
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "cross-tenant access denied"


def test_apply_tenant_filter_adds_where_clause_to_raw_sql_and_blocks_mismatch() -> None:
    context = TenantContext(tenant_id="tenant-a")

    assert apply_tenant_filter("SELECT * FROM documents", context) == "SELECT * FROM documents WHERE tenant_id = 'tenant-a'"
    assert (
        apply_tenant_filter("SELECT * FROM documents ORDER BY created_at", context)
        == "SELECT * FROM documents WHERE tenant_id = 'tenant-a' ORDER BY created_at"
    )
    assert apply_tenant_filter({"status": "active"}, context) == {"status": "active", "tenant_id": "tenant-a"}

    with pytest.raises(CrossTenantAccessError):
        apply_tenant_filter({"tenant_id": "tenant-b"}, context)


def test_tenant_query_filter_decorator_filters_returned_query() -> None:
    context = TenantContext(tenant_id="tenant-a")

    @tenant_query_filter()
    def build_query(tenant_context: TenantContext) -> str:
        return "SELECT * FROM documents LIMIT 10"

    assert build_query(context) == "SELECT * FROM documents WHERE tenant_id = 'tenant-a' LIMIT 10"


def test_tenant_rate_limiting_returns_429_for_exhausted_api_key() -> None:
    response = api_key_manager.create_key(
        APIKeyCreateRequest(
            name="limited key",
            tenant_id="tenant-limited",
            rate_limit_rpm=1,
            rate_limit_tpm=1,
        )
    )
    app = FastAPI()
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(TenantIsolationMiddleware, enforce_rate_limits=True)

    @app.get("/limited")
    async def limited() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    headers = {"X-API-Key": response.api_key}

    assert client.get("/limited", headers=headers).status_code == 200
    limited_response = client.get("/limited", headers=headers)
    assert limited_response.status_code == 429
    assert limited_response.headers["Retry-After"]

"""
AI Platform — API Key Routes
Task: ai-platform-4.2 (routes)
REST endpoints for API key CRUD operations.
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from app.api_keys import (
    api_key_manager,
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyInfo,
)

router = APIRouter(prefix="/auth/keys", tags=["API Keys"])


@router.post("/", response_model=APIKeyCreateResponse, status_code=201)
async def create_api_key(request: Request, body: APIKeyCreateRequest):
    """
    Create a new API key. The full key is returned ONLY in this response.
    Requires admin or owner role.
    """
    # Check authorization (must be admin or owner of the tenant)
    user_role = getattr(request.state, "role", None)
    user_tenant = getattr(request.state, "tenant_id", None)

    if user_role not in ("admin", "owner") and user_tenant != body.tenant_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions to create API keys")

    return api_key_manager.create_key(body)


@router.get("/", response_model=list[APIKeyInfo])
async def list_api_keys(
    request: Request,
    tenant_id: str,
    include_revoked: bool = False,
):
    """List all API keys for a tenant. Never returns the full key."""
    return api_key_manager.list_keys(tenant_id, include_revoked=include_revoked)


@router.get("/{key_id}", response_model=APIKeyInfo)
async def get_api_key(key_id: str):
    """Get details for a single API key."""
    info = api_key_manager.get_key_info(key_id)
    if info is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return info


@router.post("/{key_id}/rotate", response_model=APIKeyCreateResponse)
async def rotate_api_key(
    request: Request,
    key_id: str,
    expires_in_days: Optional[int] = 90,
):
    """Rotate an API key: revoke old, create new with same scope."""
    result = api_key_manager.rotate_key(key_id, expires_in_days=expires_in_days)
    if result is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return result


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(key_id: str):
    """Revoke an API key immediately."""
    success = api_key_manager.revoke_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return None


@router.post("/{key_id}/validate")
async def validate_api_key_endpoint(api_key: str):
    """Validate an API key and return its scope (internal use)."""
    record = api_key_manager.validate_key(api_key)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return {
        "valid": True,
        "key_id": record.key_id,
        "tenant_id": record.scope.tenant_id,
        "project_id": record.scope.project_id,
        "rate_limit_rpm": record.scope.rate_limit_rpm,
    }

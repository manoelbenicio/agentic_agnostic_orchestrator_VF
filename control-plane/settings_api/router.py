"""FastAPI routes for tenant settings, profile, integrations, and API tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field


class SettingEntry(BaseModel):
    key: str = Field(min_length=1)
    value: str


class SettingsResponse(BaseModel):
    tenant_id: str
    settings: dict[str, str]


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    settings: dict[str, str]


class ProfileResponse(BaseModel):
    tenant_id: str
    profile: dict[str, str]


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    profile: dict[str, str]


class IntegrationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class IntegrationResponse(BaseModel):
    integration_id: str
    tenant_id: str
    name: str
    provider: str
    config: dict[str, Any]
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None


class TokenCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    expires_at: datetime | None = None


class TokenResponse(BaseModel):
    token_id: str
    tenant_id: str
    name: str
    prefix: str
    created_at: datetime | None
    expires_at: datetime | None


class TokenCreateResponse(TokenResponse):
    """Returned only on creation — includes the raw token value (shown once)."""

    raw_token: str


def build_settings_router(get_state: Callable[[], Any]) -> APIRouter:
    """Build the settings router using the app state dependency."""
    router = APIRouter(prefix="/settings", tags=["settings"])

    def repository(state: Any = Depends(get_state)) -> Any:
        repo = getattr(state, "settings_repo", None)
        if repo is None:
            raise HTTPException(status_code=503, detail="settings repository unavailable")
        return repo

    # ── General Settings ─────────────────────────────────────────────

    @router.get("", response_model=SettingsResponse)
    def get_settings(
        tenant_id: str = "tenant-a",
        repo: Any = Depends(repository),
    ) -> SettingsResponse:
        records = repo.get_settings(tenant_id)
        settings_dict = {r.key: r.value for r in records if not r.key.startswith("profile.")}
        return SettingsResponse(tenant_id=tenant_id, settings=settings_dict)

    @router.patch("", response_model=SettingsResponse)
    def update_settings(
        request: SettingsUpdateRequest,
        repo: Any = Depends(repository),
    ) -> SettingsResponse:
        for key, value in request.settings.items():
            repo.upsert_setting(tenant_id=request.tenant_id, key=key, value=value)
        records = repo.get_settings(request.tenant_id)
        settings_dict = {r.key: r.value for r in records if not r.key.startswith("profile.")}
        return SettingsResponse(tenant_id=request.tenant_id, settings=settings_dict)

    # ── Profile ──────────────────────────────────────────────────────

    @router.get("/profile", response_model=ProfileResponse)
    def get_profile(
        tenant_id: str = "tenant-a",
        repo: Any = Depends(repository),
    ) -> ProfileResponse:
        profile = repo.get_profile(tenant_id)
        return ProfileResponse(tenant_id=tenant_id, profile=profile)

    @router.patch("/profile", response_model=ProfileResponse)
    def update_profile(
        request: ProfileUpdateRequest,
        repo: Any = Depends(repository),
    ) -> ProfileResponse:
        profile = repo.upsert_profile(request.tenant_id, request.profile)
        return ProfileResponse(tenant_id=request.tenant_id, profile=profile)

    # ── Integrations ─────────────────────────────────────────────────

    @router.get("/integrations", response_model=list[IntegrationResponse])
    def list_integrations(
        tenant_id: str = "tenant-a",
        repo: Any = Depends(repository),
    ) -> list[IntegrationResponse]:
        return [_integration(i) for i in repo.list_integrations(tenant_id)]

    @router.post(
        "/integrations",
        response_model=IntegrationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_integration(
        request: IntegrationCreateRequest,
        repo: Any = Depends(repository),
    ) -> IntegrationResponse:
        record = repo.create_integration(
            tenant_id=request.tenant_id,
            name=request.name,
            provider=request.provider,
            config=request.config,
            enabled=request.enabled,
        )
        return _integration(record)

    # ── API Tokens ───────────────────────────────────────────────────

    @router.get("/api-tokens", response_model=list[TokenResponse])
    def list_tokens(
        tenant_id: str = "tenant-a",
        repo: Any = Depends(repository),
    ) -> list[TokenResponse]:
        return [_token(t) for t in repo.list_tokens(tenant_id)]

    @router.post(
        "/api-tokens",
        response_model=TokenCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_token(
        request: TokenCreateRequest,
        repo: Any = Depends(repository),
    ) -> TokenCreateResponse:
        raw_token = secrets.token_urlsafe(32)
        prefix = raw_token[:8]
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        record = repo.create_token(
            tenant_id=request.tenant_id,
            name=request.name,
            token_hash=token_hash,
            prefix=prefix,
            expires_at=request.expires_at,
        )
        return TokenCreateResponse(
            token_id=record.token_id,
            tenant_id=record.tenant_id,
            name=record.name,
            prefix=prefix,
            created_at=record.created_at,
            expires_at=record.expires_at,
            raw_token=raw_token,
        )

    @router.delete("/api-tokens/{id}", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_token(
        id: str,
        repo: Any = Depends(repository),
    ) -> None:
        record = repo.revoke_token(id)
        if record is None:
            raise HTTPException(status_code=404, detail="token not found")

    return router


def _integration(record: Any) -> IntegrationResponse:
    return IntegrationResponse(
        integration_id=record.integration_id,
        tenant_id=record.tenant_id,
        name=record.name,
        provider=record.provider,
        config=record.config,
        enabled=record.enabled,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _token(record: Any) -> TokenResponse:
    return TokenResponse(
        token_id=record.token_id,
        tenant_id=record.tenant_id,
        name=record.name,
        prefix=record.prefix,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )

"""Domain models for tenant settings, integrations, and API tokens."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SettingRecord:
    """A single key-value setting scoped to a tenant."""

    setting_id: str
    tenant_id: str
    key: str
    value: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IntegrationRecord:
    """An external integration configured for a tenant."""

    integration_id: str
    tenant_id: str
    name: str
    provider: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ApiTokenRecord:
    """An API token issued to a tenant."""

    token_id: str
    tenant_id: str
    name: str
    token_hash: str
    prefix: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

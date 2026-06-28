"""Domain models for multi-tenant resource isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any


class TenantNamespaceStatus(StrEnum):
    """Lifecycle status for a tenant namespace."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEPROVISIONING = "deprovisioning"
    ARCHIVED = "archived"


class ResourceDimension(StrEnum):
    """Dimensions along which resource quotas are enforced."""

    CPU_MILLICORES = "cpu_millicores"
    MEMORY_BYTES = "memory_bytes"
    STORAGE_BYTES = "storage_bytes"


# ── Default quota tiers ──────────────────────────────────────────────────

DEFAULT_QUOTAS: dict[str, dict[ResourceDimension, int]] = {
    "free": {
        ResourceDimension.CPU_MILLICORES: 1_000,        # 1 vCPU
        ResourceDimension.MEMORY_BYTES: 2_147_483_648,   # 2 GiB
        ResourceDimension.STORAGE_BYTES: 10_737_418_240,  # 10 GiB
    },
    "standard": {
        ResourceDimension.CPU_MILLICORES: 4_000,         # 4 vCPU
        ResourceDimension.MEMORY_BYTES: 8_589_934_592,   # 8 GiB
        ResourceDimension.STORAGE_BYTES: 53_687_091_200,  # 50 GiB
    },
    "enterprise": {
        ResourceDimension.CPU_MILLICORES: 16_000,        # 16 vCPU
        ResourceDimension.MEMORY_BYTES: 34_359_738_368,  # 32 GiB
        ResourceDimension.STORAGE_BYTES: 214_748_364_800, # 200 GiB
    },
}


@dataclass(frozen=True, slots=True)
class ResourceQuota:
    """Hard cap for a single resource dimension within a tenant namespace."""

    dimension: ResourceDimension
    limit: int
    request: int = 0  # guaranteed minimum (Kubernetes-style request)

    @property
    def label(self) -> str:
        """Human-readable label for the dimension."""
        return self.dimension.value.replace("_", " ").title()


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    """Current usage for a single resource dimension."""

    dimension: ResourceDimension
    limit: int
    used: int
    reserved: int = 0

    @property
    def available(self) -> int:
        return max(0, self.limit - self.used - self.reserved)

    @property
    def utilization_pct(self) -> Decimal:
        if self.limit == 0:
            return Decimal("0")
        return (Decimal(str(self.used)) / Decimal(str(self.limit)) * 100).quantize(
            Decimal("0.01")
        )

    @property
    def exhausted(self) -> bool:
        return self.available <= 0


@dataclass(frozen=True, slots=True)
class TenantNamespace:
    """Isolated namespace for a single tenant.

    Each namespace carries its own resource quotas, isolation labels, and
    status tracking.
    """

    namespace_id: str
    tenant_id: str
    display_name: str
    status: TenantNamespaceStatus = TenantNamespaceStatus.ACTIVE
    tier: str = "standard"
    quotas: list[ResourceQuota] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == TenantNamespaceStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class QuotaEnforcementResult:
    """Result of a quota admission check."""

    admitted: bool
    tenant_id: str
    namespace_id: str
    violations: list[str] = field(default_factory=list)
    usage_snapshot: list[QuotaUsage] = field(default_factory=list)

    @property
    def denied(self) -> bool:
        return not self.admitted


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0)

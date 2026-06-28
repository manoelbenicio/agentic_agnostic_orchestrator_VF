"""Multi-tenant resource isolation for the AOP control plane.

Each tenant gets an isolated namespace with enforced CPU, memory, and storage
quotas.  The isolation service rejects operations that would exceed a
tenant's quota without touching the underlying workloads.
"""

from .models import (
    QuotaEnforcementResult,
    QuotaUsage,
    ResourceDimension,
    ResourceQuota,
    TenantNamespace,
    TenantNamespaceStatus,
)
from .repository import TenantNamespaceRepository
from .router import build_tenants_router
from .schema import init_schema
from .service import TenantIsolationService

__all__ = [
    "QuotaEnforcementResult",
    "QuotaUsage",
    "ResourceDimension",
    "ResourceQuota",
    "TenantIsolationService",
    "TenantNamespace",
    "TenantNamespaceRepository",
    "TenantNamespaceStatus",
    "build_tenants_router",
    "init_schema",
]

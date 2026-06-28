"""Tenant isolation service — admission control and quota enforcement.

The service answers the question: "Can this tenant consume N units of
resource X right now?" without touching the underlying infrastructure.

Usage::

    service = TenantIsolationService(repo)

    # Before allocating resources to a tenant operation:
    result = service.check_admission(tenant_id, {
        ResourceDimension.CPU_MILLICORES: 500,
        ResourceDimension.MEMORY_BYTES: 1_073_741_824,
    })
    if result.denied:
        raise QuotaExceeded(result.violations)

    # After actual allocation succeeds:
    service.consume(tenant_id, ResourceDimension.CPU_MILLICORES, 500)
"""

from __future__ import annotations

import logging
from typing import Any

from .models import (
    DEFAULT_QUOTAS,
    QuotaEnforcementResult,
    QuotaUsage,
    ResourceDimension,
    ResourceQuota,
    TenantNamespace,
    TenantNamespaceStatus,
)
from .repository import TenantNamespaceRepository

logger = logging.getLogger(__name__)


class TenantIsolationService:
    """Admission control and lifecycle management for tenant namespaces."""

    def __init__(self, repo: TenantNamespaceRepository) -> None:
        self.repo = repo

    # ── Namespace lifecycle ──────────────────────────────────────────────

    def provision_namespace(
        self,
        *,
        tenant_id: str,
        display_name: str,
        tier: str = "standard",
        labels: dict[str, str] | None = None,
        annotations: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TenantNamespace:
        """Provision a new isolated namespace for a tenant.

        If the tenant already has a namespace, return it without creating a
        duplicate (idempotent).
        """
        existing = self.repo.get_by_tenant(tenant_id)
        if existing is not None:
            logger.info(
                "namespace already exists for tenant %s: %s",
                tenant_id,
                existing.namespace_id,
            )
            return existing

        namespace = self.repo.create_namespace(
            tenant_id=tenant_id,
            display_name=display_name,
            tier=tier,
            labels=labels,
            annotations=annotations,
            metadata=metadata,
        )
        logger.info(
            "provisioned namespace %s for tenant %s (tier=%s)",
            namespace.namespace_id,
            tenant_id,
            tier,
        )
        return namespace

    def suspend_namespace(self, tenant_id: str) -> TenantNamespace | None:
        """Suspend a tenant's namespace (blocks new resource allocation)."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        updated = self.repo.update_status(ns.namespace_id, TenantNamespaceStatus.SUSPENDED)
        if updated:
            logger.info("suspended namespace %s for tenant %s", ns.namespace_id, tenant_id)
        return updated

    def reactivate_namespace(self, tenant_id: str) -> TenantNamespace | None:
        """Reactivate a suspended namespace."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        updated = self.repo.update_status(ns.namespace_id, TenantNamespaceStatus.ACTIVE)
        if updated:
            logger.info("reactivated namespace %s for tenant %s", ns.namespace_id, tenant_id)
        return updated

    def deprovision_namespace(self, tenant_id: str) -> TenantNamespace | None:
        """Mark a namespace for deprovisioning."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        updated = self.repo.update_status(
            ns.namespace_id, TenantNamespaceStatus.DEPROVISIONING
        )
        if updated:
            logger.info(
                "marked namespace %s for deprovisioning (tenant %s)",
                ns.namespace_id,
                tenant_id,
            )
        return updated

    # ── Quota management ─────────────────────────────────────────────────

    def update_quota(
        self,
        tenant_id: str,
        dimension: ResourceDimension,
        limit: int,
        request: int = 0,
    ) -> ResourceQuota | None:
        """Update a quota for a tenant's namespace.  Returns None if not found."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        quota = self.repo.set_quota(ns.namespace_id, dimension, limit, request)
        logger.info(
            "updated quota %s=%d for tenant %s (ns=%s)",
            dimension.value,
            limit,
            tenant_id,
            ns.namespace_id,
        )
        return quota

    def apply_tier(self, tenant_id: str, tier: str) -> TenantNamespace | None:
        """Apply a predefined quota tier to a tenant's namespace."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        tier_quotas = DEFAULT_QUOTAS.get(tier)
        if tier_quotas is None:
            raise ValueError(
                f"unknown tier {tier!r}; available: {sorted(DEFAULT_QUOTAS)}"
            )
        for dimension, limit in tier_quotas.items():
            self.repo.set_quota(ns.namespace_id, dimension, limit)
        logger.info("applied tier %s to tenant %s (ns=%s)", tier, tenant_id, ns.namespace_id)
        return self.repo.get_namespace(ns.namespace_id)

    # ── Admission control ────────────────────────────────────────────────

    def check_admission(
        self,
        tenant_id: str,
        requested: dict[ResourceDimension, int],
        *,
        action: str = "resource_allocation",
    ) -> QuotaEnforcementResult:
        """Check whether a resource request fits within the tenant's quotas.

        This is a **read-only** check.  Call :meth:`consume` after the
        actual allocation succeeds.
        """
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return QuotaEnforcementResult(
                admitted=False,
                tenant_id=tenant_id,
                namespace_id="",
                violations=[f"no namespace found for tenant {tenant_id}"],
            )

        if not ns.is_active:
            return QuotaEnforcementResult(
                admitted=False,
                tenant_id=tenant_id,
                namespace_id=ns.namespace_id,
                violations=[
                    f"namespace {ns.namespace_id} is {ns.status.value} — "
                    f"resource allocation is blocked"
                ],
            )

        usage_list = self.repo.get_usage(ns.namespace_id)
        usage_map = {u.dimension: u for u in usage_list}
        violations: list[str] = []
        snapshot: list[QuotaUsage] = []

        for dimension, amount in requested.items():
            usage = usage_map.get(dimension)
            if usage is None:
                # No usage row → check if there's a quota at all
                quotas = {q.dimension: q for q in ns.quotas}
                quota = quotas.get(dimension)
                limit = quota.limit if quota else 0
                usage = QuotaUsage(dimension=dimension, limit=limit, used=0, reserved=0)

            snapshot.append(usage)
            if amount > usage.available:
                violations.append(
                    f"{dimension.value}: requested {amount}, "
                    f"available {usage.available} "
                    f"(used={usage.used}, reserved={usage.reserved}, limit={usage.limit})"
                )

        admitted = len(violations) == 0

        # Audit
        self.repo.log_enforcement(
            namespace_id=ns.namespace_id,
            tenant_id=tenant_id,
            action=action,
            admitted=admitted,
            violations=violations,
            metadata={"requested": {d.value: a for d, a in requested.items()}},
        )

        return QuotaEnforcementResult(
            admitted=admitted,
            tenant_id=tenant_id,
            namespace_id=ns.namespace_id,
            violations=violations,
            usage_snapshot=snapshot,
        )

    # ── Usage tracking ───────────────────────────────────────────────────

    def consume(
        self,
        tenant_id: str,
        dimension: ResourceDimension,
        amount: int,
    ) -> QuotaUsage | None:
        """Record actual consumption after a successful allocation."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        return self.repo.increment_usage(ns.namespace_id, dimension, amount)

    def release(
        self,
        tenant_id: str,
        dimension: ResourceDimension,
        amount: int,
    ) -> QuotaUsage | None:
        """Release resources when a tenant operation completes."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return None
        return self.repo.increment_usage(ns.namespace_id, dimension, -amount)

    def get_usage_summary(self, tenant_id: str) -> list[QuotaUsage]:
        """Return current usage snapshot for a tenant."""
        ns = self.repo.get_by_tenant(tenant_id)
        if ns is None:
            return []
        return self.repo.get_usage(ns.namespace_id)

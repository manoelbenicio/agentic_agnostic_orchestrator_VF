"""Postgres repository for multi-tenant resource isolation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .models import (
    DEFAULT_QUOTAS,
    QuotaUsage,
    ResourceDimension,
    ResourceQuota,
    TenantNamespace,
    TenantNamespaceStatus,
)


class TenantNamespaceRepository:
    """CRUD, quota, and usage persistence for tenant namespaces."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    # ── Namespace CRUD ───────────────────────────────────────────────────

    def create_namespace(
        self,
        *,
        tenant_id: str,
        display_name: str,
        tier: str = "standard",
        labels: dict[str, str] | None = None,
        annotations: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        namespace_id: str | None = None,
    ) -> TenantNamespace:
        """Create an isolated namespace with default quotas for the tier."""
        namespace_id = namespace_id or f"ns-{uuid4().hex[:12]}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_namespaces (
                    namespace_id, tenant_id, display_name, status, tier,
                    labels, annotations, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    namespace_id,
                    tenant_id,
                    display_name,
                    TenantNamespaceStatus.ACTIVE.value,
                    tier,
                    Jsonb(labels or {}),
                    Jsonb(annotations or {}),
                    Jsonb(metadata or {}),
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("namespace insert returned no row")

            # Insert default quotas for the tier
            tier_quotas = DEFAULT_QUOTAS.get(tier, DEFAULT_QUOTAS["standard"])
            for dimension, limit in tier_quotas.items():
                cur.execute(
                    """
                    INSERT INTO tenant_resource_quotas (namespace_id, dimension, "limit", request)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (namespace_id, dimension) DO UPDATE SET
                        "limit" = EXCLUDED."limit",
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (namespace_id, dimension.value, limit, 0),
                )

            # Insert zero usage rows
            for dimension in ResourceDimension:
                cur.execute(
                    """
                    INSERT INTO tenant_resource_usage (namespace_id, dimension, used, reserved)
                    VALUES (%s, %s, 0, 0)
                    ON CONFLICT (namespace_id, dimension) DO NOTHING
                    """,
                    (namespace_id, dimension.value),
                )

        self.conn.commit()
        return self._namespace_with_quotas(row)

    def get_namespace(self, namespace_id: str) -> TenantNamespace | None:
        """Return a namespace by ID."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenant_namespaces WHERE namespace_id = %s",
                (namespace_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._namespace_with_quotas(row)

    def get_by_tenant(self, tenant_id: str) -> TenantNamespace | None:
        """Return the namespace for a tenant."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tenant_namespaces WHERE tenant_id = %s",
                (tenant_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._namespace_with_quotas(row)

    def list_namespaces(
        self,
        *,
        status: TenantNamespaceStatus | None = None,
    ) -> list[TenantNamespace]:
        """List all namespaces, optionally filtered by status."""
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = %s")
            params.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM tenant_namespaces {where} ORDER BY created_at ASC",
                params,
            )
            rows = cur.fetchall()
        return [self._namespace_with_quotas(row) for row in rows]

    def update_status(
        self,
        namespace_id: str,
        status: TenantNamespaceStatus,
    ) -> TenantNamespace | None:
        """Update the lifecycle status of a namespace."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tenant_namespaces
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE namespace_id = %s
                RETURNING *
                """,
                (status.value, namespace_id),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            return None
        return self._namespace_with_quotas(row)

    # ── Quota management ─────────────────────────────────────────────────

    def set_quota(
        self,
        namespace_id: str,
        dimension: ResourceDimension,
        limit: int,
        request: int = 0,
    ) -> ResourceQuota:
        """Set or update a quota for a dimension."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_resource_quotas (namespace_id, dimension, "limit", request)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (namespace_id, dimension) DO UPDATE SET
                    "limit" = EXCLUDED."limit",
                    request = EXCLUDED.request,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING dimension, "limit", request
                """,
                (namespace_id, dimension.value, limit, request),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("quota upsert returned no row")
        return ResourceQuota(
            dimension=ResourceDimension(row["dimension"]),
            limit=int(row["limit"]),
            request=int(row["request"]),
        )

    def get_quotas(self, namespace_id: str) -> list[ResourceQuota]:
        """Return all quotas for a namespace."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT dimension, "limit", request
                FROM tenant_resource_quotas
                WHERE namespace_id = %s
                ORDER BY dimension
                """,
                (namespace_id,),
            )
            rows = cur.fetchall()
        return [
            ResourceQuota(
                dimension=ResourceDimension(row["dimension"]),
                limit=int(row["limit"]),
                request=int(row["request"]),
            )
            for row in rows
        ]

    # ── Usage tracking ───────────────────────────────────────────────────

    def record_usage(
        self,
        namespace_id: str,
        dimension: ResourceDimension,
        used: int,
        reserved: int = 0,
    ) -> QuotaUsage:
        """Record current resource usage for a dimension."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_resource_usage (namespace_id, dimension, used, reserved, measured_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (namespace_id, dimension) DO UPDATE SET
                    used = EXCLUDED.used,
                    reserved = EXCLUDED.reserved,
                    measured_at = CURRENT_TIMESTAMP
                """,
                (namespace_id, dimension.value, used, reserved),
            )
            # Fetch the quota limit for this dimension
            cur.execute(
                """
                SELECT "limit" FROM tenant_resource_quotas
                WHERE namespace_id = %s AND dimension = %s
                """,
                (namespace_id, dimension.value),
            )
            quota_row = cur.fetchone()
        self.conn.commit()
        limit = int(quota_row["limit"]) if quota_row else 0
        return QuotaUsage(
            dimension=dimension,
            limit=limit,
            used=used,
            reserved=reserved,
        )

    def get_usage(self, namespace_id: str) -> list[QuotaUsage]:
        """Return current usage for all dimensions in a namespace."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    u.dimension,
                    COALESCE(q."limit", 0) AS "limit",
                    u.used,
                    u.reserved
                FROM tenant_resource_usage u
                LEFT JOIN tenant_resource_quotas q
                    ON u.namespace_id = q.namespace_id
                    AND u.dimension = q.dimension
                WHERE u.namespace_id = %s
                ORDER BY u.dimension
                """,
                (namespace_id,),
            )
            rows = cur.fetchall()
        return [
            QuotaUsage(
                dimension=ResourceDimension(row["dimension"]),
                limit=int(row["limit"]),
                used=int(row["used"]),
                reserved=int(row["reserved"]),
            )
            for row in rows
        ]

    def increment_usage(
        self,
        namespace_id: str,
        dimension: ResourceDimension,
        delta: int,
    ) -> QuotaUsage:
        """Atomically increment usage for a dimension (can be negative to release)."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_resource_usage (namespace_id, dimension, used, reserved)
                VALUES (%s, %s, GREATEST(0, %s), 0)
                ON CONFLICT (namespace_id, dimension) DO UPDATE SET
                    used = GREATEST(0, tenant_resource_usage.used + %s),
                    measured_at = CURRENT_TIMESTAMP
                RETURNING used, reserved
                """,
                (namespace_id, dimension.value, delta, delta),
            )
            usage_row = cur.fetchone()
            cur.execute(
                """
                SELECT "limit" FROM tenant_resource_quotas
                WHERE namespace_id = %s AND dimension = %s
                """,
                (namespace_id, dimension.value),
            )
            quota_row = cur.fetchone()
        self.conn.commit()
        return QuotaUsage(
            dimension=dimension,
            limit=int(quota_row["limit"]) if quota_row else 0,
            used=int(usage_row["used"]) if usage_row else 0,
            reserved=int(usage_row["reserved"]) if usage_row else 0,
        )

    # ── Audit log ────────────────────────────────────────────────────────

    def log_enforcement(
        self,
        *,
        namespace_id: str,
        tenant_id: str,
        action: str,
        admitted: bool,
        dimension: str | None = None,
        requested: int | None = None,
        available: int | None = None,
        violations: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a quota enforcement decision."""
        audit_id = f"qa-{uuid4().hex[:12]}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenant_quota_audit_log (
                    audit_id, namespace_id, tenant_id, action, admitted,
                    dimension, requested, available, violations, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    audit_id,
                    namespace_id,
                    tenant_id,
                    action,
                    admitted,
                    dimension,
                    requested,
                    available,
                    Jsonb(violations or []),
                    Jsonb(metadata or {}),
                ),
            )
        self.conn.commit()

    # ── Internal helpers ─────────────────────────────────────────────────

    def _namespace_with_quotas(self, row: dict[str, Any]) -> TenantNamespace:
        """Build a TenantNamespace with its quotas loaded."""
        namespace_id = str(row["namespace_id"])
        quotas = self.get_quotas(namespace_id)
        return TenantNamespace(
            namespace_id=namespace_id,
            tenant_id=str(row["tenant_id"]),
            display_name=str(row["display_name"]),
            status=TenantNamespaceStatus(str(row["status"])),
            tier=str(row.get("tier", "standard")),
            quotas=quotas,
            labels=dict(row.get("labels") or {}),
            annotations=dict(row.get("annotations") or {}),
            metadata=dict(row.get("metadata") or {}),
            created_at=_dt(row.get("created_at")),
            updated_at=_dt(row.get("updated_at")),
        )


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return None

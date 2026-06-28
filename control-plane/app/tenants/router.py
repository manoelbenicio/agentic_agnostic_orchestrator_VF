"""FastAPI routes for multi-tenant resource isolation."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .models import (
    DEFAULT_QUOTAS,
    QuotaEnforcementResult,
    ResourceDimension,
    TenantNamespaceStatus,
)
from .service import TenantIsolationService


# ── Request / Response schemas ───────────────────────────────────────────

class NamespaceCreateRequest(BaseModel):
    tenant_id: str
    display_name: str
    tier: str = "standard"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuotaUpdateRequest(BaseModel):
    dimension: ResourceDimension
    limit: int
    request: int = 0


class TierApplyRequest(BaseModel):
    tier: str


class AdmissionCheckRequest(BaseModel):
    requested: dict[ResourceDimension, int]
    action: str = "resource_allocation"


class UsageRecordRequest(BaseModel):
    dimension: ResourceDimension
    amount: int


# ── Router builder ───────────────────────────────────────────────────────

def build_tenants_router(
    get_state: Callable[[], Any],
    *,
    prefix: str = "/api/tenants",
) -> APIRouter:
    """Build tenant isolation API routes."""
    router = APIRouter(prefix=prefix, tags=["tenants"])

    def _service(state: Any) -> TenantIsolationService:
        svc = getattr(state, "tenant_isolation_service", None)
        if svc is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "tenant_isolation_unavailable"},
            )
        return svc

    # ── Namespace CRUD ───────────────────────────────────────────────

    @router.post("/namespaces")
    def create_namespace(
        request: NamespaceCreateRequest,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Provision an isolated namespace for a tenant."""
        service = _service(state)
        ns = service.provision_namespace(
            tenant_id=request.tenant_id,
            display_name=request.display_name,
            tier=request.tier,
            labels=request.labels,
            annotations=request.annotations,
            metadata=request.metadata,
        )
        return _namespace_response(ns)

    @router.get("/namespaces")
    def list_namespaces(
        status: str | None = None,
        state: Any = Depends(get_state),
    ) -> list[dict[str, Any]]:
        """List all tenant namespaces."""
        service = _service(state)
        filter_status = TenantNamespaceStatus(status) if status else None
        namespaces = service.repo.list_namespaces(status=filter_status)
        return [_namespace_response(ns) for ns in namespaces]

    @router.get("/namespaces/{tenant_id}")
    def get_namespace(
        tenant_id: str,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Get the namespace for a tenant."""
        service = _service(state)
        ns = service.repo.get_by_tenant(tenant_id)
        if ns is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return _namespace_response(ns)

    @router.post("/namespaces/{tenant_id}/suspend")
    def suspend_namespace(
        tenant_id: str,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Suspend a tenant namespace (blocks resource allocation)."""
        service = _service(state)
        ns = service.suspend_namespace(tenant_id)
        if ns is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return _namespace_response(ns)

    @router.post("/namespaces/{tenant_id}/reactivate")
    def reactivate_namespace(
        tenant_id: str,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Reactivate a suspended namespace."""
        service = _service(state)
        ns = service.reactivate_namespace(tenant_id)
        if ns is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return _namespace_response(ns)

    @router.post("/namespaces/{tenant_id}/deprovision")
    def deprovision_namespace(
        tenant_id: str,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Mark a namespace for deprovisioning."""
        service = _service(state)
        ns = service.deprovision_namespace(tenant_id)
        if ns is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return _namespace_response(ns)

    # ── Quotas ───────────────────────────────────────────────────────

    @router.get("/namespaces/{tenant_id}/quotas")
    def get_quotas(
        tenant_id: str,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Get resource quotas for a tenant."""
        service = _service(state)
        ns = service.repo.get_by_tenant(tenant_id)
        if ns is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        quotas = service.repo.get_quotas(ns.namespace_id)
        return {
            "tenant_id": tenant_id,
            "namespace_id": ns.namespace_id,
            "tier": ns.tier,
            "quotas": [
                {
                    "dimension": q.dimension.value,
                    "limit": q.limit,
                    "request": q.request,
                    "label": q.label,
                }
                for q in quotas
            ],
        }

    @router.put("/namespaces/{tenant_id}/quotas")
    def update_quota(
        tenant_id: str,
        request: QuotaUpdateRequest,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Update a resource quota for a tenant."""
        service = _service(state)
        quota = service.update_quota(
            tenant_id,
            request.dimension,
            request.limit,
            request.request,
        )
        if quota is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return {
            "tenant_id": tenant_id,
            "dimension": quota.dimension.value,
            "limit": quota.limit,
            "request": quota.request,
        }

    @router.post("/namespaces/{tenant_id}/quotas/apply-tier")
    def apply_tier(
        tenant_id: str,
        request: TierApplyRequest,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Apply a predefined quota tier to a tenant."""
        service = _service(state)
        try:
            ns = service.apply_tier(tenant_id, request.tier)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if ns is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return _namespace_response(ns)

    @router.get("/tiers")
    def list_tiers() -> dict[str, Any]:
        """List available quota tiers with their default limits."""
        return {
            "tiers": {
                tier: {dim.value: limit for dim, limit in quotas.items()}
                for tier, quotas in DEFAULT_QUOTAS.items()
            }
        }

    # ── Usage & admission ────────────────────────────────────────────

    @router.get("/namespaces/{tenant_id}/usage")
    def get_usage(
        tenant_id: str,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Get current resource usage for a tenant."""
        service = _service(state)
        usage = service.get_usage_summary(tenant_id)
        if not usage:
            raise HTTPException(status_code=404, detail="namespace not found or no usage data")
        return {
            "tenant_id": tenant_id,
            "usage": [
                {
                    "dimension": u.dimension.value,
                    "limit": u.limit,
                    "used": u.used,
                    "reserved": u.reserved,
                    "available": u.available,
                    "utilization_pct": str(u.utilization_pct),
                    "exhausted": u.exhausted,
                }
                for u in usage
            ],
        }

    @router.post("/namespaces/{tenant_id}/admit")
    def check_admission(
        tenant_id: str,
        request: AdmissionCheckRequest,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Check whether a resource request fits within quotas (dry-run)."""
        service = _service(state)
        result = service.check_admission(
            tenant_id,
            request.requested,
            action=request.action,
        )
        status_code = 200 if result.admitted else 403
        response = {
            "admitted": result.admitted,
            "tenant_id": result.tenant_id,
            "namespace_id": result.namespace_id,
            "violations": result.violations,
            "usage_snapshot": [
                {
                    "dimension": u.dimension.value,
                    "limit": u.limit,
                    "used": u.used,
                    "reserved": u.reserved,
                    "available": u.available,
                    "utilization_pct": str(u.utilization_pct),
                }
                for u in result.usage_snapshot
            ],
        }
        if result.denied:
            raise HTTPException(status_code=403, detail=response)
        return response

    @router.post("/namespaces/{tenant_id}/consume")
    def consume_resource(
        tenant_id: str,
        request: UsageRecordRequest,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Record resource consumption for a tenant."""
        service = _service(state)
        usage = service.consume(tenant_id, request.dimension, request.amount)
        if usage is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return {
            "tenant_id": tenant_id,
            "dimension": usage.dimension.value,
            "used": usage.used,
            "available": usage.available,
            "utilization_pct": str(usage.utilization_pct),
        }

    @router.post("/namespaces/{tenant_id}/release")
    def release_resource(
        tenant_id: str,
        request: UsageRecordRequest,
        state: Any = Depends(get_state),
    ) -> dict[str, Any]:
        """Release resources when a tenant operation completes."""
        service = _service(state)
        usage = service.release(tenant_id, request.dimension, request.amount)
        if usage is None:
            raise HTTPException(status_code=404, detail="namespace not found")
        return {
            "tenant_id": tenant_id,
            "dimension": usage.dimension.value,
            "used": usage.used,
            "available": usage.available,
            "utilization_pct": str(usage.utilization_pct),
        }

    return router


# ── Helpers ──────────────────────────────────────────────────────────────

def _namespace_response(ns: Any) -> dict[str, Any]:
    return {
        "namespace_id": ns.namespace_id,
        "tenant_id": ns.tenant_id,
        "display_name": ns.display_name,
        "status": ns.status.value if hasattr(ns.status, "value") else str(ns.status),
        "tier": ns.tier,
        "quotas": [
            {
                "dimension": q.dimension.value,
                "limit": q.limit,
                "request": q.request,
                "label": q.label,
            }
            for q in (ns.quotas or [])
        ],
        "labels": ns.labels,
        "annotations": ns.annotations,
        "metadata": ns.metadata,
        "created_at": ns.created_at.isoformat() if ns.created_at else None,
        "updated_at": ns.updated_at.isoformat() if ns.updated_at else None,
    }

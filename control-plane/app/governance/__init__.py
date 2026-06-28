"""Governance domain for the AOP control plane.

Exposes:
  * RBAC engine (Role / Permission enums, PolicyEngine, decorator)
  * Immutable audit trail with tamper-evident hash chain
  * Cost allocation, aggregation, and budget alerting

Modules:
    rbac             - role/permission definitions and enforcement
    audit_trail      - append-only AuditEntry log with integrity verification
    cost_allocation  - per-tenant/project/agent cost tracking + FastAPI router
"""

from __future__ import annotations

from .audit_trail import (
    AuditEntry,
    AuditQuery,
    AuditStorage,
    AuditTrail,
    IntegrityReport,
    InMemoryAuditStorage,
)
from .cost_allocation import (
    BudgetAlert,
    CostAggregator,
    CostBucket,
    CostEvent,
    build_governance_costs_router,
)
from .rbac import (
    Permission,
    PermissionDeniedError,
    PolicyEngine,
    PolicyRule,
    Role,
    User,
    enforce_permission,
    default_policy_engine,
)

__all__ = [
    # RBAC
    "Role",
    "Permission",
    "User",
    "PolicyEngine",
    "PolicyRule",
    "PermissionDeniedError",
    "enforce_permission",
    "default_policy_engine",
    # Audit trail
    "AuditEntry",
    "AuditQuery",
    "AuditStorage",
    "AuditTrail",
    "IntegrityReport",
    "InMemoryAuditStorage",
    # Cost allocation
    "CostEvent",
    "CostAggregator",
    "CostBucket",
    "BudgetAlert",
    "build_governance_costs_router",
]

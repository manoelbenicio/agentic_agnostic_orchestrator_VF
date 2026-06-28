"""Governance domain for the AOP control plane.

Modules:
  * :mod:`.rbac`           - static Role / Permission enums and PolicyEngine
  * :mod:`.rbac_engine`    - dynamic RBAC engine with mutable user↔role
                              assignments and custom role definitions
  * :mod:`.audit_trail`    - tamper-evident hash-chained audit log
  * :mod:`.cost_allocation` - cost tracking + budget alerting
"""

from __future__ import annotations

from .audit_trail import (
    AuditEntry,
    AuditQuery,
    AuditStorage,
    AuditTrail,
    ExportFormat,
    IntegrityReport,
    InMemoryAuditStorage,
    build_governance_audit_router,
)
from .cost_allocation import (
    BudgetAlert,
    BudgetThreshold,
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
    ROLE_PERMISSIONS,
    Role,
    User,
    enforce_permission,
    default_policy_engine,
)
from .rbac_engine import (
    AssignRoleRequest,
    CheckPermissionRequest,
    CheckResponse,
    CreateRoleRequest,
    EnforcePolicyRequest,
    EnforceResponse,
    RBACEngine,
    RoleDefinition,
    RoleKind,
    RoleResponse,
    build_governance_rbac_router,
)

__all__ = [
    # rbac (static)
    "Role",
    "Permission",
    "ROLE_PERMISSIONS",
    "User",
    "PolicyEngine",
    "PolicyRule",
    "PermissionDeniedError",
    "enforce_permission",
    "default_policy_engine",
    # rbac_engine (dynamic)
    "RBACEngine",
    "RoleKind",
    "RoleDefinition",
    "CreateRoleRequest",
    "AssignRoleRequest",
    "CheckPermissionRequest",
    "EnforcePolicyRequest",
    "RoleResponse",
    "CheckResponse",
    "EnforceResponse",
    "build_governance_rbac_router",
    # audit_trail
    "AuditEntry",
    "AuditQuery",
    "AuditStorage",
    "AuditTrail",
    "ExportFormat",
    "IntegrityReport",
    "InMemoryAuditStorage",
    "build_governance_audit_router",
    # cost_allocation
    "CostEvent",
    "CostAggregator",
    "CostBucket",
    "BudgetAlert",
    "BudgetThreshold",
    "build_governance_costs_router",
]

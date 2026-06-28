"""Dynamic RBAC engine for the AOP control plane.

Complements the static role / permission matrix in :mod:`.rbac` with
runtime-mutable user↔role assignments and custom role definitions.
:class:`RBACEngine` is the single source of truth for "which user has
which role" and "which permissions does each role grant", and writes
every check / assignment / role creation into the bound
:class:`~.audit_trail.AuditTrail`.

API surface:
  * :meth:`RBACEngine.check_permission` - ``bool`` check
  * :meth:`RBACEngine.assign_role`      - bind a role to a user
  * :meth:`RBACEngine.create_role`      - define a custom role
  * :meth:`RBACEngine.list_roles`       - enumerate built-in + custom roles
  * :meth:`RBACEngine.enforce_policy`   - action+resource → permission check

A FastAPI router exposing ``/governance/rbac`` is built by
:func:`build_governance_rbac_router`.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Sequence

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .audit_trail import AuditTrail, get_default_trail
from .rbac import Permission, ROLE_PERMISSIONS, Role

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Custom roles + assignments (in-memory, thread-safe)
# ---------------------------------------------------------------------------


class RoleKind(str, Enum):
    BUILTIN = "builtin"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    """Either a built-in :class:`Role` or a runtime-defined custom role."""

    name: str
    kind: RoleKind
    permissions: frozenset[Permission]
    description: str = ""
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "permissions": sorted(p.value for p in self.permissions),
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Action / resource → permission mapping for enforce_policy
# ---------------------------------------------------------------------------

# Resource domain keywords (first match in resource string wins).
_RESOURCE_DOMAINS: tuple[tuple[str, Permission], ...] = (
    ("registry", Permission.REGISTRY_READ),
    ("topology", Permission.TOPOLOGY_READ),
    ("provisioning", Permission.PROVISIONING_READ),
    ("governance", Permission.GOVERNANCE_AUDIT_READ),
    ("billing", Permission.BILLING_READ),
    ("agent", Permission.AGENT_READ),
    ("finops", Permission.FINOPS_READ),
    ("task", Permission.TASK_READ),
    ("user", Permission.USER_READ),
    ("settings", Permission.SETTINGS_READ),
    ("tracing", Permission.TRACING_READ),
    ("tenant", Permission.TENANT_READ),
    ("squad", Permission.SQUAD_READ),
    ("session", Permission.SESSION_READ),
    ("seat", Permission.SEAT_READ),
)

_WRITE_VERBS = {"write", "create", "update", "patch", "put", "post"}
_DELETE_VERBS = {"delete", "remove", "destroy"}
_READ_VERBS = {"read", "get", "list", "fetch"}


def _resolve_action_permission(action: str, resource: str) -> Permission | None:
    """Map a (verb, resource) pair to a :class:`Permission`.

    Returns ``None`` when the verb / resource pair cannot be mapped;
    :meth:`RBACEngine.enforce_policy` treats that as a denial.
    """
    verb = action.strip().lower().split()[0] if action else ""
    if not verb:
        return None
    for keyword, base_perm in _RESOURCE_DOMAINS:
        if keyword in resource.lower():
            if verb in _READ_VERBS:
                return base_perm
            if verb in _WRITE_VERBS:
                # The WRITE permission lives in the same domain as READ.
                write_perm_str = base_perm.value.replace(":read", ":write")
                try:
                    return Permission(write_perm_str)
                except ValueError:
                    return None
            if verb in _DELETE_VERBS:
                delete_perm_str = base_perm.value.replace(":read", ":delete")
                try:
                    return Permission(delete_perm_str)
                except ValueError:
                    return None
            # Unknown verb within a known domain — deny.
            return None
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    permissions: list[Permission]
    description: str = Field(default="", max_length=512)


class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=256)
    role: str = Field(min_length=1, max_length=64)


class CheckPermissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=256)
    permission: Permission


class EnforcePolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=256)
    action: str = Field(min_length=1, max_length=64)
    resource: str = Field(min_length=1, max_length=512)


class RoleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: dict[str, Any] | None = None
    roles: list[dict[str, Any]] | None = None


class CheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    granted: bool
    user_id: str
    permission: str
    role: str | None = None


class EnforceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    granted: bool
    user_id: str
    action: str
    resource: str
    resolved_permission: str | None = None
    role: str | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RBACEngine:
    """Dynamic role management + permission enforcement.

    Built-in roles come from :class:`Role` and :data:`ROLE_PERMISSIONS`;
    custom roles are added at runtime via :meth:`create_role`. Per-user
    role assignments are mutable via :meth:`assign_role`. Every mutation
    and every check is appended to the bound :class:`AuditTrail`.
    """

    def __init__(
        self,
        audit_trail: AuditTrail | None = None,
        default_role: Role | str = Role.VIEWER,
    ) -> None:
        # NOTE: use `is not None` because empty AuditTrail is falsy via __len__.
        self._audit_trail: AuditTrail = audit_trail if audit_trail is not None else get_default_trail()
        self._default_role_name: str = default_role.value if isinstance(default_role, Role) else default_role
        self._custom_roles: dict[str, RoleDefinition] = {}
        self._user_roles: dict[str, str] = {}
        self._lock = threading.RLock()

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _builtin_definitions() -> list[RoleDefinition]:
        return [
            RoleDefinition(
                name=role.value,
                kind=RoleKind.BUILTIN,
                permissions=perms,
                description=f"built-in role with {len(perms)} permission(s)",
            )
            for role, perms in ROLE_PERMISSIONS.items()
        ]

    def _resolve_role(self, role_name: str) -> RoleDefinition | None:
        """Return the definition for ``role_name`` (built-in or custom)."""
        for definition in self._builtin_definitions():
            if definition.name == role_name:
                return definition
        with self._lock:
            return self._custom_roles.get(role_name)

    def _permissions_for(self, role_name: str) -> frozenset[Permission]:
        definition = self._resolve_role(role_name)
        return definition.permissions if definition else frozenset()

    def _effective_role(self, user_id: str) -> str:
        with self._lock:
            return self._user_roles.get(user_id, self._default_role_name)

    # ----------------------------------------------------------- create
    def create_role(
        self,
        role_name: str,
        permissions: Iterable[Permission],
        description: str = "",
    ) -> RoleDefinition:
        """Define a new custom role and return its definition.

        Raises :class:`ValueError` if ``role_name`` collides with a
        built-in role or an existing custom role.
        """
        perms = frozenset(permissions)
        for existing in self._builtin_definitions():
            if existing.name == role_name:
                raise ValueError(f"role {role_name!r} is a built-in role and cannot be redefined")
        with self._lock:
            if role_name in self._custom_roles:
                raise ValueError(f"custom role {role_name!r} already exists")
            definition = RoleDefinition(
                name=role_name,
                kind=RoleKind.CUSTOM,
                permissions=perms,
                description=description,
            )
            self._custom_roles[role_name] = definition
        self._audit_trail.log_event(
            actor="rbac_engine",
            action="rbac.role.create",
            resource=f"rbac:role:{role_name}",
            new_value={"permissions": sorted(p.value for p in perms), "description": description},
            metadata={"kind": RoleKind.CUSTOM.value},
        )
        return definition

    def delete_custom_role(self, role_name: str) -> bool:
        """Remove a custom role. Returns ``False`` if it didn't exist."""
        with self._lock:
            if role_name not in self._custom_roles:
                return False
            del self._custom_roles[role_name]
            # Users assigned to the deleted role fall back to default.
            affected = [uid for uid, r in self._user_roles.items() if r == role_name]
            for uid in affected:
                self._user_roles[uid] = self._default_role_name
        self._audit_trail.log_event(
            actor="rbac_engine",
            action="rbac.role.delete",
            resource=f"rbac:role:{role_name}",
            metadata={"affected_users": affected},
        )
        return True

    # ----------------------------------------------------------- assign
    def assign_role(self, user_id: str, role: str | Role) -> RoleDefinition:
        """Bind ``user_id`` to ``role``.

        ``role`` may be a built-in :class:`Role` enum value or any
        previously-created custom role name. Raises :class:`ValueError`
        if the role name is unknown.
        """
        role_name = role.value if isinstance(role, Role) else role
        definition = self._resolve_role(role_name)
        if definition is None:
            raise ValueError(f"unknown role: {role_name!r}")
        with self._lock:
            previous = self._user_roles.get(user_id)
            self._user_roles[user_id] = role_name
        self._audit_trail.log_event(
            actor="rbac_engine",
            action="rbac.role.assign",
            resource=f"rbac:user:{user_id}",
            old_value=previous,
            new_value=role_name,
            metadata={"previous_role": previous},
        )
        return definition

    def unassign_role(self, user_id: str) -> bool:
        """Drop the explicit role binding for ``user_id``.

        Returns ``True`` if a binding was removed; ``False`` if the user
        had no explicit binding.
        """
        with self._lock:
            previous = self._user_roles.pop(user_id, None)
        if previous is None:
            return False
        self._audit_trail.log_event(
            actor="rbac_engine",
            action="rbac.role.unassign",
            resource=f"rbac:user:{user_id}",
            old_value=previous,
            new_value=None,
        )
        return True

    def get_role(self, user_id: str) -> RoleDefinition:
        """Return the role currently effective for ``user_id`` (never raises)."""
        return self._resolve_role(self._effective_role(user_id)) or self._resolve_role(self._default_role_name)  # type: ignore[return-value]

    # ----------------------------------------------------------- list
    def list_roles(self) -> list[RoleDefinition]:
        """Return all roles: built-in first (sorted), then custom (sorted)."""
        builtins = sorted(self._builtin_definitions(), key=lambda d: d.name)
        with self._lock:
            customs = sorted(self._custom_roles.values(), key=lambda d: d.name)
        return [*builtins, *customs]

    def list_assignments(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"user_id": uid, "role": role}
                for uid, role in sorted(self._user_roles.items())
            ]

    # ----------------------------------------------------------- check
    def check_permission(
        self,
        user_id: str,
        permission: Permission,
        *,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Return ``True`` iff the user's effective role grants ``permission``."""
        role_name = self._effective_role(user_id)
        granted = permission in self._permissions_for(role_name)
        try:
            self._audit_trail.log_event(
                actor=user_id,
                action=f"permission.{'grant' if granted else 'deny'}",
                resource=f"rbac:{permission.value}",
                metadata={
                    "role": role_name,
                    "context": context or {},
                },
            )
        except Exception:  # pragma: no cover - audit must never break checks
            logger.exception("failed to record permission check")
        return granted

    def enforce_policy(
        self,
        user_id: str,
        action: str,
        resource: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Resolve ``action`` / ``resource`` to a :class:`Permission` and check it.

        Unknown verb / resource combinations map to ``None`` and result
        in a denial. The resolved permission (when known) is reported in
        the audit entry so operators can see *why* a request was denied.
        """
        permission = _resolve_action_permission(action, resource)
        if permission is None:
            self._audit_trail.log_event(
                actor=user_id,
                action="permission.deny",
                resource=f"rbac:unmapped:{action}:{resource}",
                metadata={"action": action, "resource": resource, "reason": "unmapped action/resource"},
            )
            return False
        granted = self.check_permission(user_id, permission, context=context)
        return granted

    # ----------------------------------------------------------- diagnostics
    def resolved_permission(self, action: str, resource: str) -> Permission | None:
        """Public view of the action→permission mapping (for diagnostics)."""
        return _resolve_action_permission(action, resource)


# ---------------------------------------------------------------------------
# FastAPI router (/governance/rbac)
# ---------------------------------------------------------------------------


def build_governance_rbac_router(engine: RBACEngine | None = None) -> APIRouter:
    """Build a router exposing ``/governance/rbac`` endpoints.

    Endpoints:
      * ``POST   /governance/rbac/roles``                     - create custom role
      * ``GET    /governance/rbac/roles``                     - list roles
      * ``GET    /governance/rbac/roles/{name}``              - get a single role
      * ``DELETE /governance/rbac/roles/{name}``              - delete custom role
      * ``POST   /governance/rbac/assignments``               - assign role to user
      * ``GET    /governance/rbac/assignments``               - list all assignments
      * ``GET    /governance/rbac/assignments/{user_id}``     - get user's role
      * ``DELETE /governance/rbac/assignments/{user_id}``     - unassign
      * ``POST   /governance/rbac/check``                     - check permission
      * ``POST   /governance/rbac/enforce``                   - enforce policy
    """
    router = APIRouter(prefix="/governance/rbac")
    state: dict[str, RBACEngine] = {"engine": engine if engine is not None else RBACEngine()}

    def _engine() -> RBACEngine:
        return state["engine"]

    @router.post("/roles", response_model=RoleResponse)
    def create_role(request: CreateRoleRequest) -> RoleResponse:
        try:
            definition = _engine().create_role(
                role_name=request.name,
                permissions=request.permissions,
                description=request.description,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "role_conflict", "reason": str(exc)}) from exc
        return RoleResponse(role=definition.to_dict())

    @router.get("/roles", response_model=RoleResponse)
    def list_roles() -> RoleResponse:
        return RoleResponse(roles=[definition.to_dict() for definition in _engine().list_roles()])

    @router.get("/roles/{name}", response_model=RoleResponse)
    def get_role(name: str) -> RoleResponse:
        definition = _engine()._resolve_role(name)
        if definition is None:
            raise HTTPException(status_code=404, detail={"code": "role_not_found", "name": name})
        return RoleResponse(role=definition.to_dict())

    @router.delete("/roles/{name}", response_model=RoleResponse)
    def delete_role(name: str) -> RoleResponse:
        deleted = _engine().delete_custom_role(name)
        if not deleted:
            raise HTTPException(status_code=404, detail={"code": "role_not_found", "name": name})
        return RoleResponse(role={"name": name, "deleted": True})

    @router.post("/assignments", response_model=RoleResponse)
    def assign_role(request: AssignRoleRequest) -> RoleResponse:
        try:
            definition = _engine().assign_role(request.user_id, request.role)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"code": "unknown_role", "reason": str(exc)}) from exc
        return RoleResponse(role={"user_id": request.user_id, **definition.to_dict()})

    @router.get("/assignments")
    def list_assignments() -> dict[str, Any]:
        return {"assignments": _engine().list_assignments()}

    @router.get("/assignments/{user_id}", response_model=RoleResponse)
    def get_assignment(user_id: str) -> RoleResponse:
        definition = _engine().get_role(user_id)
        return RoleResponse(role={"user_id": user_id, **definition.to_dict()})

    @router.delete("/assignments/{user_id}")
    def unassign(user_id: str) -> dict[str, Any]:
        removed = _engine().unassign_role(user_id)
        return {"user_id": user_id, "removed": removed}

    @router.post("/check", response_model=CheckResponse)
    def check(request: CheckPermissionRequest) -> CheckResponse:
        granted = _engine().check_permission(request.user_id, request.permission)
        role_name = _engine()._effective_role(request.user_id)
        return CheckResponse(
            granted=granted,
            user_id=request.user_id,
            permission=request.permission.value,
            role=role_name,
        )

    @router.post("/enforce", response_model=EnforceResponse)
    def enforce(request: EnforcePolicyRequest) -> EnforceResponse:
        permission = _engine().resolved_permission(request.action, request.resource)
        granted = _engine().enforce_policy(request.user_id, request.action, request.resource)
        role_name = _engine()._effective_role(request.user_id)
        return EnforceResponse(
            granted=granted,
            user_id=request.user_id,
            action=request.action,
            resource=request.resource,
            resolved_permission=permission.value if permission else None,
            role=role_name,
        )

    return router


__all__ = [
    "RoleKind",
    "RoleDefinition",
    "RBACEngine",
    "CreateRoleRequest",
    "AssignRoleRequest",
    "CheckPermissionRequest",
    "EnforcePolicyRequest",
    "RoleResponse",
    "CheckResponse",
    "EnforceResponse",
    "build_governance_rbac_router",
]

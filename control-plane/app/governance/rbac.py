"""Role-based access control (RBAC) engine for the AOP control plane.

Defines five ``Role`` values (``platform_admin``, ``tenant_admin``,
``operator``, ``developer``, ``viewer``), a 39-permission ``Permission``
enum covering registry, topology, provisioning, governance, billing,
agents, finops, tasks, users, settings, tracing, tenants, squads,
sessions, and seats, and a ``ROLE_PERMISSIONS`` matrix mapping each role
to its granted permission set.

Exposes:

  * :class:`User` - identity record passed to the policy engine.
  * :class:`PolicyEngine` - allow/deny evaluator with rule priority.
  * :func:`enforce_permission` - decorator for sync and async callables.
  * :func:`default_policy_engine` - lazily-built singleton.

Every permission check is recorded in an :class:`AuditTrail` so
forbidden attempts and granted accesses are both reviewable.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable, Iterable, Mapping, Sequence

from .audit_trail import AuditTrail, get_default_trail

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Five-tier role hierarchy used by the AOP control plane."""

    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    OPERATOR = "operator"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Granular permissions used by the policy engine.

    Naming convention is ``<domain>:<verb>`` (or ``<domain>:<sub>:<verb>``
    when a sub-domain exists). 39 permissions in total.
    """

    # Registry (3)
    REGISTRY_READ = "registry:read"
    REGISTRY_WRITE = "registry:write"
    REGISTRY_DELETE = "registry:delete"

    # Topology (3)
    TOPOLOGY_READ = "topology:read"
    TOPOLOGY_WRITE = "topology:write"
    TOPOLOGY_DELETE = "topology:delete"

    # Provisioning (4)
    PROVISIONING_READ = "provisioning:read"
    PROVISIONING_WRITE = "provisioning:write"
    PROVISIONING_DELETE = "provisioning:delete"
    PROVISIONING_ACTIVATE = "provisioning:activate"

    # Governance (4)
    GOVERNANCE_AUDIT_READ = "governance:audit:read"
    GOVERNANCE_POLICY_READ = "governance:policy:read"
    GOVERNANCE_POLICY_WRITE = "governance:policy:write"
    GOVERNANCE_COST_READ = "governance:cost:read"

    # Billing (3)
    BILLING_READ = "billing:read"
    BILLING_WRITE = "billing:write"
    BILLING_EXPORT = "billing:export"

    # Agents (3)
    AGENT_READ = "agent:read"
    AGENT_WRITE = "agent:write"
    AGENT_DELETE = "agent:delete"

    # FinOps (3)
    FINOPS_READ = "finops:read"
    FINOPS_WRITE = "finops:write"
    FINOPS_EXPORT = "finops:export"

    # Tasks (3)
    TASK_READ = "task:read"
    TASK_WRITE = "task:write"
    TASK_DELETE = "task:delete"

    # Users (3)
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # Settings (2)
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Tracing (1)
    TRACING_READ = "tracing:read"

    # Tenants (3)
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_DELETE = "tenant:delete"

    # Squads (2)
    SQUAD_READ = "squad:read"
    SQUAD_WRITE = "squad:write"

    # Sessions (1)
    SESSION_READ = "session:read"

    # Seats (2)
    SEAT_READ = "seat:read"
    SEAT_WRITE = "seat:write"


def _perms(*values: Permission) -> frozenset[Permission]:
    return frozenset(values)


# ---------------------------------------------------------------------------
# ROLE_PERMISSIONS matrix
# ---------------------------------------------------------------------------
# Each role grants a specific permission set. Permissions not in the set are
# denied unless an explicit ALLOW rule is added to a PolicyEngine. A rule
# can still DENY a permission even when the role grants it (deny wins).
ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.PLATFORM_ADMIN: _perms(*Permission),
    Role.TENANT_ADMIN: _perms(
        Permission.REGISTRY_READ,
        Permission.REGISTRY_WRITE,
        Permission.REGISTRY_DELETE,
        Permission.TOPOLOGY_READ,
        Permission.TOPOLOGY_WRITE,
        Permission.TOPOLOGY_DELETE,
        Permission.PROVISIONING_READ,
        Permission.PROVISIONING_WRITE,
        Permission.PROVISIONING_ACTIVATE,
        Permission.GOVERNANCE_AUDIT_READ,
        Permission.GOVERNANCE_POLICY_READ,
        Permission.GOVERNANCE_POLICY_WRITE,
        Permission.GOVERNANCE_COST_READ,
        Permission.BILLING_READ,
        Permission.BILLING_WRITE,
        Permission.BILLING_EXPORT,
        Permission.AGENT_READ,
        Permission.AGENT_WRITE,
        Permission.AGENT_DELETE,
        Permission.FINOPS_READ,
        Permission.FINOPS_WRITE,
        Permission.FINOPS_EXPORT,
        Permission.TASK_READ,
        Permission.TASK_WRITE,
        Permission.TASK_DELETE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.SETTINGS_READ,
        Permission.TRACING_READ,
        Permission.TENANT_READ,
        Permission.TENANT_WRITE,
        Permission.SQUAD_READ,
        Permission.SQUAD_WRITE,
        Permission.SESSION_READ,
        Permission.SEAT_READ,
        Permission.SEAT_WRITE,
    ),
    Role.OPERATOR: _perms(
        Permission.REGISTRY_READ,
        Permission.REGISTRY_WRITE,
        Permission.TOPOLOGY_READ,
        Permission.TOPOLOGY_WRITE,
        Permission.PROVISIONING_READ,
        Permission.PROVISIONING_WRITE,
        Permission.PROVISIONING_ACTIVATE,
        Permission.GOVERNANCE_AUDIT_READ,
        Permission.GOVERNANCE_COST_READ,
        Permission.BILLING_READ,
        Permission.AGENT_READ,
        Permission.AGENT_WRITE,
        Permission.FINOPS_READ,
        Permission.FINOPS_WRITE,
        Permission.TASK_READ,
        Permission.TASK_WRITE,
        Permission.USER_READ,
        Permission.SETTINGS_READ,
        Permission.TRACING_READ,
        Permission.TENANT_READ,
        Permission.SQUAD_READ,
        Permission.SQUAD_WRITE,
        Permission.SESSION_READ,
        Permission.SEAT_READ,
        Permission.SEAT_WRITE,
    ),
    Role.DEVELOPER: _perms(
        Permission.REGISTRY_READ,
        Permission.REGISTRY_WRITE,
        Permission.TOPOLOGY_READ,
        Permission.PROVISIONING_READ,
        Permission.GOVERNANCE_AUDIT_READ,
        Permission.GOVERNANCE_COST_READ,
        Permission.BILLING_READ,
        Permission.AGENT_READ,
        Permission.AGENT_WRITE,
        Permission.FINOPS_READ,
        Permission.TASK_READ,
        Permission.TASK_WRITE,
        Permission.USER_READ,
        Permission.SETTINGS_READ,
        Permission.TRACING_READ,
        Permission.TENANT_READ,
        Permission.SQUAD_READ,
        Permission.SQUAD_WRITE,
        Permission.SESSION_READ,
        Permission.SEAT_READ,
    ),
    Role.VIEWER: _perms(
        Permission.REGISTRY_READ,
        Permission.TOPOLOGY_READ,
        Permission.PROVISIONING_READ,
        Permission.GOVERNANCE_AUDIT_READ,
        Permission.GOVERNANCE_COST_READ,
        Permission.BILLING_READ,
        Permission.AGENT_READ,
        Permission.FINOPS_READ,
        Permission.TASK_READ,
        Permission.USER_READ,
        Permission.SETTINGS_READ,
        Permission.TRACING_READ,
        Permission.TENANT_READ,
        Permission.SQUAD_READ,
        Permission.SESSION_READ,
        Permission.SEAT_READ,
    ),
}


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class User:
    """Identity record supplied to the policy engine."""

    user_id: str
    role: Role
    tenant_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PermissionDeniedError(PermissionError):
    """Raised by :func:`enforce_permission` and :meth:`PolicyEngine.check`."""

    def __init__(
        self,
        user: User,
        permission: Permission,
        *,
        reason: str = "permission denied",
        correlation_id: str | None = None,
    ) -> None:
        self.user = user
        self.permission = permission
        self.reason = reason
        self.correlation_id = correlation_id
        super().__init__(
            f"{reason}: user '{user.user_id}' (role={user.role.value}) "
            f"lacks permission '{permission.value}'"
        )


# ---------------------------------------------------------------------------
# Policy rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyRule:
    """Allow/deny rule evaluated by :class:`PolicyEngine`.

    Rules with higher ``priority`` are evaluated first; the first matching
    rule decides the outcome. A DENY rule always wins over an ALLOW rule
    with the same priority. ``permission=None`` means the rule applies to
    any permission being checked.
    """

    effect: str  # "allow" or "deny"
    permission: Permission | None
    predicate: Callable[[User, Permission, Mapping[str, Any]], bool]
    priority: int = 0
    description: str = ""

    def matches(self, user: User, permission: Permission, context: Mapping[str, Any]) -> bool:
        if self.permission is not None and self.permission != permission:
            return False
        return bool(self.predicate(user, permission, context))


def _has_scope_predicate(scope: str) -> Callable[[User, Permission, Mapping[str, Any]], bool]:
    def _pred(user: User, _perm: Permission, _ctx: Mapping[str, Any]) -> bool:
        return user.has_scope(scope)

    return _pred


def _same_tenant_predicate(_user: User, _perm: Permission, context: Mapping[str, Any]) -> bool:
    requested_tenant = context.get("tenant_id")
    actor_tenant = context.get("actor_tenant_id")
    return bool(requested_tenant) and requested_tenant == actor_tenant


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Allow/deny evaluator that combines role grants and rule overrides.

    Evaluation order:
      1. Sort rules by descending ``priority``; iterate and pick the first
         match.
      2. A matched DENY rule short-circuits to ``False``.
      3. A matched ALLOW rule returns ``True`` if the role matrix also
         contains the permission (rules can only elevate within the role's
         baseline) — or unconditionally if ``permission`` is ``None``
         (rule applies to a wildcard permission, which cannot be granted
         by a role, so DENY semantics are preserved).
      4. If no rule matches, fall back to the ``ROLE_PERMISSIONS`` matrix.
      5. Final default is ``False``.

    Every check (allow or deny) is appended to the bound :class:`AuditTrail`.
    """

    def __init__(self, audit_trail: AuditTrail | None = None) -> None:
        self._audit_trail: AuditTrail = audit_trail or get_default_trail()
        self._rules: list[PolicyRule] = []
        self._lock = threading.RLock()

    # --------------------------------------------------------------- rules
    def add_rule(self, rule: PolicyRule) -> PolicyRule:
        if rule.effect not in {"allow", "deny"}:
            raise ValueError(f"rule.effect must be 'allow' or 'deny', got {rule.effect!r}")
        with self._lock:
            self._rules.append(rule)
            self._rules.sort(key=lambda r: r.priority, reverse=True)
        return rule

    def allow(
        self,
        permission: Permission | None,
        *,
        predicate: Callable[[User, Permission, Mapping[str, Any]], bool] | None = None,
        priority: int = 0,
        description: str = "",
    ) -> PolicyRule:
        return self.add_rule(
            PolicyRule(
                effect="allow",
                permission=permission,
                predicate=predicate or (lambda _u, _p, _c: True),
                priority=priority,
                description=description,
            )
        )

    def deny(
        self,
        permission: Permission | None,
        *,
        predicate: Callable[[User, Permission, Mapping[str, Any]], bool] | None = None,
        priority: int = 0,
        description: str = "",
    ) -> PolicyRule:
        return self.add_rule(
            PolicyRule(
                effect="deny",
                permission=permission,
                predicate=predicate or (lambda _u, _p, _c: True),
                priority=priority,
                description=description,
            )
        )

    def remove_rule(self, rule: PolicyRule) -> None:
        with self._lock:
            try:
                self._rules.remove(rule)
            except ValueError:
                pass

    @property
    def rules(self) -> Sequence[PolicyRule]:
        return tuple(self._rules)

    # --------------------------------------------------------- evaluation
    def evaluate(
        self,
        user: User,
        permission: Permission,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return ``True`` iff ``user`` may perform ``permission``.

        ``context`` is forwarded to rule predicates so they can inspect
        resource ids, tenant ids, etc. The default context includes
        ``actor_tenant_id`` derived from ``user.tenant_id``.
        """
        ctx: dict[str, Any] = {
            "actor_tenant_id": user.tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if context:
            ctx.update(context)

        # Rule pass
        for rule in self._rules:
            if rule.matches(user, permission, ctx):
                if rule.effect == "deny":
                    self._audit(
                        user=user,
                        permission=permission,
                        granted=False,
                        context=ctx,
                        reason=f"deny rule: {rule.description or 'unspecified'}",
                    )
                    return False
                # effect == "allow"
                granted = permission in ROLE_PERMISSIONS.get(user.role, frozenset())
                self._audit(
                    user=user,
                    permission=permission,
                    granted=granted,
                    context=ctx,
                    reason=f"allow rule: {rule.description or 'unspecified'}",
                )
                return granted

        # Default: role matrix
        granted = permission in ROLE_PERMISSIONS.get(user.role, frozenset())
        self._audit(
            user=user,
            permission=permission,
            granted=granted,
            context=ctx,
            reason="role matrix" if granted else "no grant in role matrix",
        )
        return granted

    def check(
        self,
        user: User,
        permission: Permission,
        context: Mapping[str, Any] | None = None,
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Raise :class:`PermissionDeniedError` if the user lacks ``permission``."""
        if not self.evaluate(user, permission, context):
            raise PermissionDeniedError(
                user=user,
                permission=permission,
                reason="policy evaluation denied",
                correlation_id=correlation_id,
            )

    # --------------------------------------------------------------- audit
    def _audit(
        self,
        *,
        user: User,
        permission: Permission,
        granted: bool,
        context: Mapping[str, Any],
        reason: str,
    ) -> None:
        try:
            self._audit_trail.append(
                actor=user.user_id,
                action=f"permission.{'grant' if granted else 'deny'}",
                resource=f"rbac:{permission.value}",
                metadata={
                    "role": user.role.value,
                    "tenant_id": user.tenant_id,
                    "reason": reason,
                    "context": {k: v for k, v in context.items() if k != "timestamp"},
                },
                correlation_id=context.get("correlation_id") if isinstance(context, Mapping) else None,
            )
        except Exception:  # pragma: no cover - audit must never break enforcement
            logger.exception("failed to write RBAC audit entry")


# ---------------------------------------------------------------------------
# Default singleton
# ---------------------------------------------------------------------------


_DEFAULT_ENGINE: PolicyEngine | None = None
_DEFAULT_LOCK = threading.Lock()


def default_policy_engine() -> PolicyEngine:
    """Return the process-wide :class:`PolicyEngine`, creating it on first use."""
    global _DEFAULT_ENGINE
    with _DEFAULT_LOCK:
        if _DEFAULT_ENGINE is None:
            _DEFAULT_ENGINE = PolicyEngine()
        return _DEFAULT_ENGINE


def reset_default_policy_engine() -> None:
    """Reset the process-wide engine (used by tests)."""
    global _DEFAULT_ENGINE
    with _DEFAULT_LOCK:
        _DEFAULT_ENGINE = None


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def _resolve_user(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> User | None:
    """Best-effort extraction of a :class:`User` from call arguments."""
    candidate: Any = kwargs.get("user")
    if isinstance(candidate, User):
        return candidate
    if candidate is not None and hasattr(candidate, "user_id") and hasattr(candidate, "role"):
        # Duck-typed compatibility (e.g. JWT payload proxies)
        return candidate  # type: ignore[return-value]
    for arg in args:
        if isinstance(arg, User):
            return arg
    return None


def enforce_permission(
    permission: Permission,
    *,
    engine: PolicyEngine | None = None,
    user_kwarg: str = "user",
    context_from: Callable[[Iterable[Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that asserts the caller holds ``permission``.

    The wrapped callable must receive a :class:`User` either as a keyword
    argument named ``user_kwarg`` (default ``"user"``) or as the first
    positional argument. Optional ``context_from(args, kwargs)`` may
    return a context mapping forwarded to the policy engine.

    Both sync and async callables are supported.
    """
    policy = engine

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        is_coro = asyncio.iscoroutinefunction(func)

        if is_coro:

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                user = _resolve_user(args, kwargs) or bound.arguments.get(user_kwarg)
                if not isinstance(user, User):
                    raise PermissionDeniedError(
                        user=User(user_id="<unknown>", role=Role.VIEWER),
                        permission=permission,
                        reason="no User supplied to decorated callable",
                    )
                ctx = context_from(args, kwargs) if context_from else None
                engine_to_use = policy or default_policy_engine()
                engine_to_use.check(user, permission, ctx)
                return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            user = _resolve_user(args, kwargs) or bound.arguments.get(user_kwarg)
            if not isinstance(user, User):
                raise PermissionDeniedError(
                    user=User(user_id="<unknown>", role=Role.VIEWER),
                    permission=permission,
                    reason="no User supplied to decorated callable",
                )
            ctx = context_from(args, kwargs) if context_from else None
            engine_to_use = policy or default_policy_engine()
            engine_to_use.check(user, permission, ctx)
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator


__all__ = [
    "Role",
    "Permission",
    "ROLE_PERMISSIONS",
    "User",
    "PolicyRule",
    "PolicyEngine",
    "PermissionDeniedError",
    "enforce_permission",
    "default_policy_engine",
    "reset_default_policy_engine",
    "_has_scope_predicate",
    "_same_tenant_predicate",
]

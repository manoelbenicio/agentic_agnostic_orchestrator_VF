from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
import re
from typing import Any, TypeVar

import jwt
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.api_keys import APIKeyRecord, api_key_manager
from app.auth import ALGORITHM, SECRET_KEY
from app.rate_limiter import KeyScope, check_rate_limit


PUBLIC_PATHS = {"/health", "/metrics", "/docs", "/openapi.json"}
PUBLIC_PREFIXES = ("/auth/device/",)
F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    project_id: str | None = None
    subject: str | None = None
    role: str | None = None
    auth_type: str = "anonymous"
    api_key_id: str | None = None
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100_000

    @classmethod
    def from_jwt_payload(cls, payload: dict[str, Any]) -> "TenantContext":
        tenant_id = str(payload.get("tenant_id") or "").strip()
        if not tenant_id:
            raise ValueError("JWT is missing tenant_id claim")
        project_id = payload.get("project_id")
        return cls(
            tenant_id=tenant_id,
            project_id=str(project_id).strip() if project_id else None,
            subject=str(payload.get("sub") or "").strip() or None,
            role=str(payload.get("role") or "").strip() or None,
            auth_type="jwt",
            rate_limit_rpm=int(payload.get("rate_limit_rpm") or 60),
            rate_limit_tpm=int(payload.get("rate_limit_tpm") or 100_000),
        )

    @classmethod
    def from_api_key(cls, record: APIKeyRecord) -> "TenantContext":
        return cls(
            tenant_id=record.scope.tenant_id,
            project_id=record.scope.project_id,
            subject=record.key_id,
            role="api_key",
            auth_type="api_key",
            api_key_id=record.key_id,
            rate_limit_rpm=record.scope.rate_limit_rpm,
            rate_limit_tpm=record.scope.rate_limit_tpm,
        )

    def assert_access(self, *, tenant_id: str | None = None, project_id: str | None = None) -> None:
        if tenant_id is not None and tenant_id != self.tenant_id:
            raise CrossTenantAccessError("cross-tenant access denied")
        if project_id is not None and self.project_id is not None and project_id != self.project_id:
            raise CrossTenantAccessError("cross-project access denied")


class CrossTenantAccessError(PermissionError):
    pass


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, enforce_rate_limits: bool = True) -> None:
        super().__init__(app)
        self.enforce_rate_limits = enforce_rate_limits

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if _is_public_request(request):
            return await call_next(request)

        context = _context_from_api_key(request) or _context_from_bearer_token(request)
        if context is not None:
            _attach_context(request, context)
            if self.enforce_rate_limits:
                limited = await _enforce_tenant_rate_limits(context)
                if limited is not None:
                    return limited

        response = await call_next(request)
        return response


def get_tenant_context(request: Request) -> TenantContext:
    context = getattr(request.state, "tenant_context", None)
    if not isinstance(context, TenantContext):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="tenant context is required")
    return context


def prevent_cross_tenant_access(
    request: Request,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> TenantContext:
    context = get_tenant_context(request)
    try:
        context.assert_access(tenant_id=tenant_id, project_id=project_id)
    except CrossTenantAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return context


def tenant_query_filter(
    *,
    query_arg: str = "query",
    tenant_column: str = "tenant_id",
    context_arg: str = "tenant_context",
) -> Callable[[F], F]:
    """Decorator that injects tenant filtering into query arguments or results."""

    def decorator(func: F) -> F:
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            context = _tenant_context_from_call(args, kwargs, context_arg)
            if query_arg in kwargs:
                kwargs[query_arg] = apply_tenant_filter(kwargs[query_arg], context, tenant_column=tenant_column)
            result = func(*args, **kwargs)
            if query_arg not in kwargs:
                return apply_tenant_filter(result, context, tenant_column=tenant_column)
            return result

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            context = _tenant_context_from_call(args, kwargs, context_arg)
            if query_arg in kwargs:
                kwargs[query_arg] = apply_tenant_filter(kwargs[query_arg], context, tenant_column=tenant_column)
            result = await func(*args, **kwargs)
            if query_arg not in kwargs:
                return apply_tenant_filter(result, context, tenant_column=tenant_column)
            return result

        if _is_async_callable(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def apply_tenant_filter(query: Any, tenant_context: TenantContext, *, tenant_column: str = "tenant_id") -> Any:
    if query is None:
        return query
    if isinstance(query, str):
        return _apply_raw_sql_tenant_filter(query, tenant_context.tenant_id, tenant_column=tenant_column)
    if hasattr(query, "where"):
        column = _resolve_tenant_column(query, tenant_column)
        if column is None:
            raise ValueError(f"query does not expose tenant column {tenant_column!r}")
        return query.where(column == tenant_context.tenant_id)
    if isinstance(query, dict):
        existing = query.get(tenant_column)
        if existing is not None and existing != tenant_context.tenant_id:
            raise CrossTenantAccessError("cross-tenant query denied")
        return {**query, tenant_column: tenant_context.tenant_id}
    raise TypeError(f"unsupported query type for tenant filtering: {type(query).__name__}")


def enforce_tenant_record_access(record: Any, tenant_context: TenantContext, *, tenant_attr: str = "tenant_id") -> None:
    tenant_id = record.get(tenant_attr) if isinstance(record, dict) else getattr(record, tenant_attr, None)
    tenant_context.assert_access(tenant_id=tenant_id)


def _context_from_api_key(request: Request) -> TenantContext | None:
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None
    record = api_key_manager.validate_key(api_key)
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    return TenantContext.from_api_key(record)


def _context_from_bearer_token(request: Request) -> TenantContext | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    try:
        return TenantContext.from_jwt_payload(payload)
    except ValueError:
        return None


def _attach_context(request: Request, context: TenantContext) -> None:
    request.state.tenant_context = context
    request.state.tenant_id = context.tenant_id
    request.state.project_id = context.project_id
    if context.subject:
        request.state.user_id = context.subject
    if context.role:
        request.state.role = context.role
    request.state.key_scope = KeyScope(
        tenant_id=context.tenant_id,
        api_key=context.api_key_id or f"jwt_{context.subject or 'anonymous'}",
        rpm_limit=context.rate_limit_rpm,
        tpm_limit=context.rate_limit_tpm,
    )


async def _enforce_tenant_rate_limits(context: TenantContext) -> JSONResponse | None:
    key_identifier = context.api_key_id or f"jwt:{context.subject or context.tenant_id}"
    allowed, retry_after = await check_rate_limit(
        identifier=f"{context.auth_type}:{key_identifier}",
        limit_per_minute=context.rate_limit_rpm,
        cost=1,
        limit_type="RPM",
    )
    if not allowed:
        return _rate_limit_response("RPM limit exceeded for tenant credential", retry_after)

    tenant_allowed, tenant_retry_after = await check_rate_limit(
        identifier=f"tenant:{context.tenant_id}",
        limit_per_minute=max(context.rate_limit_rpm * 10, context.rate_limit_rpm),
        cost=1,
        limit_type="RPM",
    )
    if not tenant_allowed:
        return _rate_limit_response("RPM limit exceeded for tenant", tenant_retry_after)

    tpm_allowed, tpm_retry_after = await check_rate_limit(
        identifier=f"{context.auth_type}:{key_identifier}",
        limit_per_minute=context.rate_limit_tpm,
        cost=1,
        limit_type="TPM",
    )
    if not tpm_allowed:
        return _rate_limit_response("TPM limit exhausted for tenant credential", tpm_retry_after)
    return None


def _rate_limit_response(message: str, retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "Too Many Requests", "message": message},
        headers={"Retry-After": str(retry_after)},
    )


def _apply_raw_sql_tenant_filter(query: str, tenant_id: str, *, tenant_column: str) -> str:
    if re.search(rf"\b{re.escape(tenant_column)}\b\s*=", query, flags=re.IGNORECASE):
        return query
    insertion = f"{tenant_column} = '{_escape_sql_literal(tenant_id)}'"
    if re.search(r"\bwhere\b", query, flags=re.IGNORECASE):
        return re.sub(r"\bwhere\b", f"WHERE {insertion} AND", query, count=1, flags=re.IGNORECASE)
    match = re.search(r"\b(order\s+by|group\s+by|limit|offset)\b", query, flags=re.IGNORECASE)
    if match:
        return f"{query[:match.start()].rstrip()} WHERE {insertion} {query[match.start():].lstrip()}"
    return f"{query.rstrip()} WHERE {insertion}"


def _resolve_tenant_column(query: Any, tenant_column: str) -> Any:
    selected_columns = getattr(query, "selected_columns", None)
    if selected_columns is not None and tenant_column in selected_columns:
        return selected_columns[tenant_column]
    column_descriptions = getattr(query, "column_descriptions", None) or []
    for description in column_descriptions:
        entity = description.get("entity")
        if entity is not None and hasattr(entity, tenant_column):
            return getattr(entity, tenant_column)
    table = getattr(query, "table", None)
    if table is not None and hasattr(table, "c") and tenant_column in table.c:
        return table.c[tenant_column]
    return None


def _tenant_context_from_call(args: tuple[Any, ...], kwargs: dict[str, Any], context_arg: str) -> TenantContext:
    context = kwargs.get(context_arg)
    if isinstance(context, TenantContext):
        return context
    for value in args:
        if isinstance(value, TenantContext):
            return value
        state = getattr(value, "state", None)
        if state is not None and isinstance(getattr(state, "tenant_context", None), TenantContext):
            return state.tenant_context
    raise RuntimeError("TenantContext is required for tenant query filtering")


def _is_async_callable(func: Callable[..., Any]) -> bool:
    return getattr(func, "__code__", None) is not None and bool(func.__code__.co_flags & 0x80)


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _is_public_request(request: Request) -> bool:
    return (
        request.method == "OPTIONS"
        or request.url.path in PUBLIC_PATHS
        or request.url.path.startswith(PUBLIC_PREFIXES)
        or request.url.path == "/auth/token"
    )

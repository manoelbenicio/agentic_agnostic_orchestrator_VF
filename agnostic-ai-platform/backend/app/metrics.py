from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.token_tracker import (
    litellm_failure_callback as _token_tracker_litellm_failure_callback,
    record_llm_token_usage as _record_llm_token_usage,
    token_tracker_metrics,
)

METRICS_REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "agnosticai_http_requests_total",
    "Total HTTP requests processed by the backend.",
    ("method", "path", "status"),
    registry=METRICS_REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "agnosticai_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ("method", "path"),
    registry=METRICS_REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_ERRORS_TOTAL = Counter(
    "agnosticai_http_errors_total",
    "Total HTTP requests completed with 4xx or 5xx status codes.",
    ("method", "path", "status"),
    registry=METRICS_REGISTRY,
)

HTTP_ACTIVE_CONNECTIONS = Gauge(
    "agnosticai_http_active_connections",
    "HTTP requests currently being processed by method and path.",
    ("method", "path"),
    registry=METRICS_REGISTRY,
)

LLM_TOKEN_USAGE = Gauge(
    "agnosticai_llm_token_usage",
    "Last observed LLM token usage by provider, model, workspace, user, and token type.",
    ("provider", "model", "workspace", "user", "token_type"),
    registry=METRICS_REGISTRY,
)

LLM_TOKEN_USAGE_TOTAL = Gauge(
    "agnosticai_llm_token_usage_total",
    "Last observed total LLM token usage by provider, model, workspace, and user.",
    ("provider", "model", "workspace", "user"),
    registry=METRICS_REGISTRY,
)

LLM_FALLBACK_TOTAL = Counter(
    "agnosticai_llm_fallback_total",
    "Total LLM fallback attempts from one model to another.",
    ("from_model", "to_model"),
    registry=METRICS_REGISTRY,
)

ACTIVE_AGENTS = Gauge(
    "agnosticai_active_agents",
    "Currently active agents by workspace.",
    ("workspace",),
    registry=METRICS_REGISTRY,
)

WEBSOCKET_CONNECTIONS = Gauge(
    "agnosticai_websocket_connections",
    "Currently open websocket connections by workspace.",
    ("workspace",),
    registry=METRICS_REGISTRY,
)


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, excluded_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self.excluded_paths = excluded_paths or {"/metrics"}

    async def dispatch(self, request: Request, call_next: Callable[[Request], object]) -> Response:
        if request.url.path in self.excluded_paths:
            response = await call_next(request)
            return response  # type: ignore[return-value]

        method = request.method
        start = perf_counter()
        status = "500"
        path = request.url.path
        HTTP_ACTIVE_CONNECTIONS.labels(method=method, path=path).inc()

        try:
            response = await call_next(request)
            status = str(response.status_code)
            path = _route_path(request)
            return response  # type: ignore[return-value]
        except Exception:
            path = _route_path(request)
            raise
        finally:
            elapsed = perf_counter() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(elapsed)
            if int(status) >= 400:
                HTTP_ERRORS_TOTAL.labels(method=method, path=path, status=status).inc()
            HTTP_ACTIVE_CONNECTIONS.labels(method=method, path=request.url.path).dec()


def register_litellm_success_callback() -> bool:
    """Register LiteLLM callbacks that feed Prometheus counters and gauges."""
    try:
        import litellm
    except ImportError:
        return False

    _append_callback(litellm, "success_callback", litellm_success_callback)
    _append_callback(litellm, "failure_callback", litellm_failure_callback)
    return True


def record_llm_token_usage(
    *,
    model: str,
    workspace: str = "default",
    user: str = "anonymous",
    provider: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    cost_usd: object = None,
):
    usage = _record_llm_token_usage(
        model=model,
        workspace=workspace,
        user=user,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
    )
    set_llm_token_usage(
        provider=usage.provider,
        model=usage.model,
        workspace=usage.workspace,
        user=usage.user,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )
    return usage


def litellm_success_callback(*args: Any, **callback_kwargs: Any) -> None:
    kwargs, response = _litellm_callback_payload(args, callback_kwargs)
    metadata = _metadata_from_kwargs(kwargs)
    usage = _get_value(response, "usage") or {}
    model = str(_get_value(response, "model") or _get_value(kwargs, "model") or _get_value(metadata, "model") or "unknown")
    record_llm_token_usage(
        provider=str(_get_value(metadata, "provider") or _infer_provider(model)),
        model=model,
        workspace=str(_get_value(metadata, "workspace", "workspace_id") or "default"),
        user=str(_get_value(metadata, "user", "user_id") or _get_value(kwargs, "user") or "anonymous"),
        prompt_tokens=_int_value(_get_value(usage, "prompt_tokens", "input_tokens")),
        completion_tokens=_int_value(_get_value(usage, "completion_tokens", "output_tokens")),
        total_tokens=_int_value(_get_value(usage, "total_tokens")) or None,
        cost_usd=_litellm_cost(kwargs, response),
    )


def litellm_failure_callback(*args: Any, **callback_kwargs: Any) -> None:
    _token_tracker_litellm_failure_callback(*args, **callback_kwargs)


def record_llm_fallback(*, from_model: str, to_model: str) -> None:
    LLM_FALLBACK_TOTAL.labels(from_model=from_model, to_model=to_model).inc()


def set_llm_token_usage(
    *,
    provider: str,
    model: str,
    workspace: str,
    user: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
) -> None:
    labels = {
        "provider": provider or "unknown",
        "model": model or "unknown",
        "workspace": workspace or "default",
        "user": user or "anonymous",
    }
    prompt_tokens = max(int(prompt_tokens or 0), 0)
    completion_tokens = max(int(completion_tokens or 0), 0)
    total = max(int(total_tokens if total_tokens is not None else prompt_tokens + completion_tokens), 0)
    LLM_TOKEN_USAGE.labels(**labels, token_type="prompt").set(prompt_tokens)
    LLM_TOKEN_USAGE.labels(**labels, token_type="completion").set(completion_tokens)
    LLM_TOKEN_USAGE.labels(**labels, token_type="total").set(total)
    LLM_TOKEN_USAGE_TOTAL.labels(**labels).set(total)


def set_active_agents(*, workspace: str, count: int) -> None:
    ACTIVE_AGENTS.labels(workspace=workspace).set(count)


def set_websocket_connections(*, workspace: str, count: int) -> None:
    WEBSOCKET_CONNECTIONS.labels(workspace=workspace).set(count)


def prometheus_response() -> Response:
    return Response(generate_latest(METRICS_REGISTRY) + token_tracker_metrics(), media_type=CONTENT_TYPE_LATEST)


def _litellm_callback_payload(args: tuple[Any, ...], callback_kwargs: dict[str, Any]) -> tuple[Any, Any]:
    kwargs = callback_kwargs.get("kwargs")
    response = (
        callback_kwargs.get("completion_response")
        or callback_kwargs.get("response_obj")
        or callback_kwargs.get("response")
        or callback_kwargs.get("output")
    )
    if kwargs is None and args:
        kwargs = args[0]
    if response is None and len(args) > 1:
        response = args[1]
    return kwargs or {}, response or {}


def _metadata_from_kwargs(kwargs: Any) -> Any:
    metadata = _get_value(kwargs, "metadata")
    if metadata:
        return metadata
    litellm_params = _get_value(kwargs, "litellm_params") or {}
    return _get_value(litellm_params, "metadata") or {}


def _litellm_cost(kwargs: Any, response: Any) -> Any:
    cost = _get_value(kwargs, "response_cost", "completion_cost", "cost")
    if cost is not None:
        return cost
    hidden_params = _get_value(response, "_hidden_params") or {}
    return _get_value(hidden_params, "response_cost", "completion_cost", "cost")


def _get_value(source: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(source, dict) and key in source:
            return source[key]
        if hasattr(source, key):
            return getattr(source, key)
    if hasattr(source, "model_dump"):
        dumped = source.model_dump()
        if isinstance(dumped, dict):
            return _get_value(dumped, *keys)
    return None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _infer_provider(model: str | None) -> str:
    normalized = (model or "").lower()
    if normalized.startswith("gpt-") or normalized.startswith("o1") or normalized.startswith("o3"):
        return "openai"
    if normalized.startswith("claude-"):
        return "anthropic"
    if normalized.startswith("gemini-"):
        return "google"
    return "unknown"


def _append_callback(module: Any, name: str, callback: Any) -> None:
    callbacks = getattr(module, name, None)
    if callbacks is None:
        callbacks = []
        setattr(module, name, callbacks)
    if not isinstance(callbacks, list):
        callbacks = [callbacks]
        setattr(module, name, callbacks)
    if callback not in callbacks:
        callbacks.append(callback)

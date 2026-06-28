from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
import os
from time import perf_counter
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

try:
    from opentelemetry import context, propagate, trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Span, SpanKind, Status, StatusCode
except ImportError:  # pragma: no cover - only used when optional deps are absent.
    context = None  # type: ignore[assignment]
    propagate = None  # type: ignore[assignment]
    trace = None  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    Span = Any  # type: ignore[misc, assignment]
    SpanKind = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]

from app.token_tracker import calculate_cost_usd, infer_provider


DEFAULT_SERVICE_NAME = "agnosticai-backend"
TRACER_NAME = "agnosticai.llm"

_OTEL_CONFIGURED = False
_INSTRUMENTED_APPS: set[int] = set()


def setup_opentelemetry(app: FastAPI | None = None) -> bool:
    """Configure OpenTelemetry tracing and optionally instrument FastAPI."""
    global _OTEL_CONFIGURED

    if trace is None:
        logger.info("OpenTelemetry packages are not installed; tracing disabled")
        return False

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    enabled = os.getenv("AOP_OTEL_ENABLED")
    traces_exporter = os.getenv("OTEL_TRACES_EXPORTER", "")
    if enabled is not None and enabled.lower() in {"0", "false", "no", "off", "none"}:
        return False
    if enabled is None and not endpoint and "otlp" not in traces_exporter.lower():
        return False

    if not _OTEL_CONFIGURED:
        service_name = os.getenv("OTEL_SERVICE_NAME") or os.getenv("AOP_OTEL_SERVICE_NAME") or DEFAULT_SERVICE_NAME
        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": os.getenv("AOP_ENV", os.getenv("ENVIRONMENT", "local")),
            }
        )
        provider = TracerProvider(resource=resource)
        exporter_kwargs = {"endpoint": endpoint} if endpoint else {}
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**exporter_kwargs)))
        trace.set_tracer_provider(provider)
        _OTEL_CONFIGURED = True

    if app is not None and id(app) not in _INSTRUMENTED_APPS:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=trace.get_tracer_provider())
        _INSTRUMENTED_APPS.add(id(app))

    return True


def get_tracer() -> Any:
    if trace is None:
        return _NoopTracer()
    return trace.get_tracer(TRACER_NAME)


def inject_trace_context(headers: MutableMapping[str, str] | None = None) -> dict[str, str]:
    carrier = dict(headers or {})
    if propagate is not None:
        propagate.inject(carrier)
    return carrier


def extract_trace_context(headers: Mapping[str, str]) -> Any:
    if propagate is None or context is None:
        return None
    return propagate.extract(dict(headers))


@contextmanager
def llm_request_span(
    *,
    model: str,
    provider: str | None = None,
    workspace: str = "default",
    user: str = "anonymous",
    metadata: Mapping[str, Any] | None = None,
) -> Any:
    start = perf_counter()
    resolved_model = model or "unknown"
    resolved_provider = provider or infer_provider(resolved_model)
    with get_tracer().start_as_current_span("llm.request", kind=_span_kind_client()) as span:
        _set_common_attributes(
            span,
            model=resolved_model,
            provider=resolved_provider,
            workspace=workspace,
            user=user,
            metadata=metadata,
        )
        try:
            yield span
        except Exception as exc:
            _mark_span_error(span, exc)
            raise
        finally:
            _safe_set_attribute(span, "llm.latency_ms", round((perf_counter() - start) * 1000, 3))


def record_llm_request_span(
    *,
    model: str,
    provider: str | None = None,
    workspace: str = "default",
    user: str = "anonymous",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    cost_usd: Decimal | float | int | str | None = None,
    latency_ms: float | None = None,
    error: BaseException | str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    resolved_model = model or "unknown"
    resolved_provider = provider or infer_provider(resolved_model)
    prompt = _int_value(prompt_tokens)
    completion = _int_value(completion_tokens)
    total = _int_value(total_tokens) if total_tokens is not None else prompt + completion
    cost = _decimal_or_none(cost_usd)
    if cost is None:
        cost = calculate_cost_usd(model=resolved_model, prompt_tokens=prompt, completion_tokens=completion)

    with get_tracer().start_as_current_span("llm.request", kind=_span_kind_client()) as span:
        _set_common_attributes(
            span,
            model=resolved_model,
            provider=resolved_provider,
            workspace=workspace,
            user=user,
            metadata=metadata,
        )
        _safe_set_attribute(span, "llm.prompt_tokens", prompt)
        _safe_set_attribute(span, "llm.completion_tokens", completion)
        _safe_set_attribute(span, "llm.total_tokens", total)
        _safe_set_attribute(span, "llm.cost_usd", float(cost))
        _safe_set_attribute(span, "gen_ai.usage.input_tokens", prompt)
        _safe_set_attribute(span, "gen_ai.usage.output_tokens", completion)
        if latency_ms is not None:
            _safe_set_attribute(span, "llm.latency_ms", round(float(latency_ms), 3))
        if error is not None:
            _mark_span_error(span, error)


def litellm_success_tracing_callback(*args: Any, **callback_kwargs: Any) -> None:
    try:
        kwargs, response = _litellm_callback_payload(args, callback_kwargs)
        metadata = _metadata_from_kwargs(kwargs)
        usage = _get_value(response, "usage") or {}
        model = str(_get_value(response, "model") or _get_value(kwargs, "model") or _get_value(metadata, "model") or "unknown")
        prompt_tokens = _int_value(_get_value(usage, "prompt_tokens", "input_tokens"))
        completion_tokens = _int_value(_get_value(usage, "completion_tokens", "output_tokens"))
        total_tokens = _int_value(_get_value(usage, "total_tokens")) or prompt_tokens + completion_tokens
        record_llm_request_span(
            provider=str(_get_value(metadata, "provider") or infer_provider(model)),
            model=model,
            workspace=str(_get_value(metadata, "workspace", "workspace_id") or "default"),
            user=str(_get_value(metadata, "user", "user_id") or _get_value(kwargs, "user") or "anonymous"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=_litellm_cost(kwargs, response),
            latency_ms=_litellm_latency_ms(kwargs, callback_kwargs),
            metadata=metadata if isinstance(metadata, Mapping) else None,
        )
    except Exception:
        logger.warning("failed to record LiteLLM tracing span", exc_info=True)


def litellm_failure_tracing_callback(*args: Any, **callback_kwargs: Any) -> None:
    try:
        kwargs, _response = _litellm_callback_payload(args, callback_kwargs)
        metadata = _metadata_from_kwargs(kwargs)
        model = str(_get_value(kwargs, "model") or _get_value(metadata, "model") or "unknown")
        error = _get_value(callback_kwargs, "exception", "error") or "unknown"
        record_llm_request_span(
            provider=str(_get_value(metadata, "provider") or infer_provider(model)),
            model=model,
            workspace=str(_get_value(metadata, "workspace", "workspace_id") or "default"),
            user=str(_get_value(metadata, "user", "user_id") or _get_value(kwargs, "user") or "anonymous"),
            latency_ms=_litellm_latency_ms(kwargs, callback_kwargs),
            error=error,
            metadata=metadata if isinstance(metadata, Mapping) else None,
        )
    except Exception:
        logger.warning("failed to record LiteLLM failure tracing span", exc_info=True)


def register_litellm_tracing_callbacks() -> bool:
    try:
        import litellm
    except ImportError:
        logger.info("LiteLLM is not installed; tracing callbacks not registered")
        return False

    _append_callback(litellm, "success_callback", litellm_success_tracing_callback)
    _append_callback(litellm, "failure_callback", litellm_failure_tracing_callback)
    return True


def _set_common_attributes(
    span: Any,
    *,
    model: str,
    provider: str,
    workspace: str,
    user: str,
    metadata: Mapping[str, Any] | None,
) -> None:
    _safe_set_attribute(span, "llm.model", model)
    _safe_set_attribute(span, "llm.provider", provider)
    _safe_set_attribute(span, "llm.workspace", workspace or "default")
    _safe_set_attribute(span, "llm.user", user or "anonymous")
    _safe_set_attribute(span, "gen_ai.system", provider)
    _safe_set_attribute(span, "gen_ai.request.model", model)
    if metadata:
        request_id = metadata.get("request_id") or metadata.get("correlation_id")
        if request_id:
            _safe_set_attribute(span, "llm.request_id", str(request_id))


def _mark_span_error(span: Any, error: BaseException | str) -> None:
    error_type = type(error).__name__ if isinstance(error, BaseException) else str(error)[:80]
    _safe_set_attribute(span, "llm.error", True)
    _safe_set_attribute(span, "llm.error_type", error_type)
    if isinstance(error, BaseException) and hasattr(span, "record_exception"):
        span.record_exception(error)
    if Status is not None and StatusCode is not None and hasattr(span, "set_status"):
        span.set_status(Status(StatusCode.ERROR, str(error)))


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


def _litellm_cost(kwargs: Any, response: Any) -> Decimal | None:
    cost = _get_value(kwargs, "response_cost", "completion_cost", "cost")
    if cost is not None:
        return _decimal_or_none(cost)
    hidden_params = _get_value(response, "_hidden_params") or {}
    return _decimal_or_none(_get_value(hidden_params, "response_cost", "completion_cost", "cost"))


def _litellm_latency_ms(kwargs: Any, callback_kwargs: Mapping[str, Any]) -> float | None:
    start = _get_value(callback_kwargs, "start_time") or _get_value(kwargs, "start_time")
    end = _get_value(callback_kwargs, "end_time") or _get_value(kwargs, "end_time")
    if start is None or end is None:
        return None
    if isinstance(start, datetime) and isinstance(end, datetime):
        return max((end - start).total_seconds() * 1000, 0)
    try:
        return max((float(end) - float(start)) * 1000, 0)
    except (TypeError, ValueError):
        return None


def _get_value(source: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(source, Mapping) and key in source:
            return source[key]
        if hasattr(source, key):
            return getattr(source, key)
    if hasattr(source, "model_dump"):
        dumped = source.model_dump()
        if isinstance(dumped, Mapping):
            return _get_value(dumped, *keys)
    return None


def _int_value(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _safe_set_attribute(span: Any, key: str, value: Any) -> None:
    if hasattr(span, "set_attribute"):
        span.set_attribute(key, value)


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


def _span_kind_client() -> Any:
    return SpanKind.CLIENT if SpanKind is not None else None


class _NoopSpan:
    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def record_exception(self, exception: BaseException) -> None:
        return None

    def set_status(self, status: Any) -> None:
        return None


class _NoopTracer:
    def start_as_current_span(self, name: str, kind: Any = None) -> _NoopSpan:
        return _NoopSpan()

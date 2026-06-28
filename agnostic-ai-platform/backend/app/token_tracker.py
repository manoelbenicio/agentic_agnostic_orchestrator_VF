from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import logging
from typing import Any

from prometheus_client import CollectorRegistry, Counter, generate_latest


logger = logging.getLogger(__name__)

TOKEN_TRACKER_REGISTRY = CollectorRegistry()

MODEL_PRICES_PER_1K_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.00060")),
    "gpt-4o": (Decimal("0.00500"), Decimal("0.01500")),
    "gpt-3.5-turbo": (Decimal("0.00050"), Decimal("0.00150")),
    "claude-3-5-sonnet": (Decimal("0.00300"), Decimal("0.01500")),
    "claude-3-haiku": (Decimal("0.00025"), Decimal("0.00125")),
    "gemini-1.5-flash": (Decimal("0.000075"), Decimal("0.00030")),
    "gemini-1.5-pro": (Decimal("0.00125"), Decimal("0.00500")),
}

LLM_REQUESTS_TOTAL = Counter(
    "agnosticai_llm_requests_total",
    "Total LiteLLM requests observed by callback status.",
    ("provider", "model", "workspace", "user", "status"),
    registry=TOKEN_TRACKER_REGISTRY,
)

LLM_TOKENS_TOTAL = Counter(
    "agnosticai_llm_tokens_total",
    "Total LLM tokens used by model, workspace, user, provider, and token type.",
    ("provider", "model", "workspace", "user", "token_type"),
    registry=TOKEN_TRACKER_REGISTRY,
)

LLM_INPUT_TOKENS_TOTAL = Counter(
    "agnosticai_llm_input_tokens_total",
    "Total LLM input tokens reported by LiteLLM success callbacks.",
    ("provider", "model", "workspace", "user"),
    registry=TOKEN_TRACKER_REGISTRY,
)

LLM_OUTPUT_TOKENS_TOTAL = Counter(
    "agnosticai_llm_output_tokens_total",
    "Total LLM output tokens reported by LiteLLM success callbacks.",
    ("provider", "model", "workspace", "user"),
    registry=TOKEN_TRACKER_REGISTRY,
)

LLM_COST_USD_TOTAL = Counter(
    "agnosticai_llm_cost_usd_total",
    "Total LLM cost in USD reported or calculated by LiteLLM callbacks.",
    ("provider", "model", "workspace", "user"),
    registry=TOKEN_TRACKER_REGISTRY,
)

LLM_FAILURE_TOTAL = Counter(
    "agnosticai_llm_failure_total",
    "Total LiteLLM failures observed by callback.",
    ("provider", "model", "workspace", "user", "error_type"),
    registry=TOKEN_TRACKER_REGISTRY,
)


@dataclass(frozen=True, slots=True)
class TokenUsage:
    provider: str
    model: str
    workspace: str
    user: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Decimal


def record_llm_token_usage(
    *,
    model: str,
    workspace: str = "default",
    user: str = "anonymous",
    provider: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    cost_usd: Decimal | float | int | str | None = None,
) -> TokenUsage:
    model = model or "unknown"
    provider = provider or infer_provider(model)
    workspace = workspace or "default"
    user = user or "anonymous"
    prompt_tokens = max(int(prompt_tokens or 0), 0)
    completion_tokens = max(int(completion_tokens or 0), 0)
    total = max(int(total_tokens if total_tokens is not None else prompt_tokens + completion_tokens), 0)
    cost = _decimal_or_none(cost_usd)
    if cost is None:
        cost = calculate_cost_usd(model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)

    labels = {"provider": provider, "model": model, "workspace": workspace, "user": user}
    LLM_REQUESTS_TOTAL.labels(**labels, status="success").inc()
    if prompt_tokens:
        LLM_TOKENS_TOTAL.labels(**labels, token_type="prompt").inc(prompt_tokens)
        LLM_INPUT_TOKENS_TOTAL.labels(**labels).inc(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS_TOTAL.labels(**labels, token_type="completion").inc(completion_tokens)
        LLM_OUTPUT_TOKENS_TOTAL.labels(**labels).inc(completion_tokens)
    if total:
        LLM_TOKENS_TOTAL.labels(**labels, token_type="total").inc(total)
    if cost > 0:
        LLM_COST_USD_TOTAL.labels(**labels).inc(float(cost))

    return TokenUsage(
        provider=provider,
        model=model,
        workspace=workspace,
        user=user,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total,
        cost_usd=cost,
    )


def calculate_cost_usd(*, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    input_price, output_price = MODEL_PRICES_PER_1K_TOKENS.get(model, (Decimal("0"), Decimal("0")))
    return (
        Decimal(prompt_tokens) * input_price / Decimal(1000)
        + Decimal(completion_tokens) * output_price / Decimal(1000)
    ).quantize(Decimal("0.00000001"))


def infer_provider(model: str | None) -> str:
    normalized = (model or "").lower()
    if normalized.startswith("gpt-") or normalized.startswith("o1") or normalized.startswith("o3"):
        return "openai"
    if normalized.startswith("claude-"):
        return "anthropic"
    if normalized.startswith("gemini-"):
        return "google"
    return "unknown"


def litellm_success_callback(*args: Any, **callback_kwargs: Any) -> None:
    try:
        kwargs, response = _litellm_callback_payload(args, callback_kwargs)
        usage = _get_value(response, "usage") or {}
        prompt_tokens = _int_value(_get_value(usage, "prompt_tokens", "input_tokens"))
        completion_tokens = _int_value(_get_value(usage, "completion_tokens", "output_tokens"))
        total_tokens = _int_value(_get_value(usage, "total_tokens")) or prompt_tokens + completion_tokens
        metadata = _metadata_from_kwargs(kwargs)
        model = str(
            _get_value(response, "model")
            or _get_value(kwargs, "model")
            or _get_value(metadata, "model")
            or "unknown"
        )
        record_llm_token_usage(
            provider=str(_get_value(metadata, "provider") or infer_provider(model)),
            model=model,
            workspace=str(_get_value(metadata, "workspace", "workspace_id") or "default"),
            user=str(_get_value(metadata, "user", "user_id") or _get_value(kwargs, "user") or "anonymous"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=_litellm_cost(kwargs, response),
        )
    except Exception:
        logger.warning("failed to record LiteLLM success metrics", exc_info=True)


def litellm_failure_callback(*args: Any, **callback_kwargs: Any) -> None:
    try:
        kwargs, response = _litellm_callback_payload(args, callback_kwargs)
        metadata = _metadata_from_kwargs(kwargs)
        model = str(_get_value(kwargs, "model") or _get_value(metadata, "model") or "unknown")
        provider = str(_get_value(metadata, "provider") or infer_provider(model))
        workspace = str(_get_value(metadata, "workspace", "workspace_id") or "default")
        user = str(_get_value(metadata, "user", "user_id") or _get_value(kwargs, "user") or "anonymous")
        error = (
            _get_value(callback_kwargs, "exception", "error")
            or _get_value(response, "exception", "error")
            or "unknown"
        )
        error_type = type(error).__name__ if not isinstance(error, str) else error[:80]
        LLM_REQUESTS_TOTAL.labels(provider, model, workspace, user, "failure").inc()
        LLM_FAILURE_TOTAL.labels(provider, model, workspace, user, error_type).inc()
    except Exception:
        logger.warning("failed to record LiteLLM failure metrics", exc_info=True)


def register_litellm_callbacks() -> bool:
    try:
        import litellm
    except ImportError:
        logger.info("LiteLLM is not installed; token tracking callbacks not registered")
        return False

    _append_callback(litellm, "success_callback", litellm_success_callback)
    _append_callback(litellm, "failure_callback", litellm_failure_callback)
    return True


def token_tracker_metrics() -> bytes:
    return generate_latest(TOKEN_TRACKER_REGISTRY)


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


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None

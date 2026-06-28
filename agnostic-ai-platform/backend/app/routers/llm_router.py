"""LLM router — agnostic provider routing via LiteLLM.

Exposes ``POST /api/llm/complete`` which routes a chat-completion request to
OpenAI, Google (Gemini) or Anthropic through LiteLLM's provider prefix
mechanism (``openai/``, ``gemini/``, ``anthropic/``). The caller may either pass
an explicit provider-qualified model (``anthropic/claude-sonnet-4-5``) or a
bare model name plus a ``provider`` hint, in which case the router resolves
the LiteLLM prefix.

A fallback chain may be supplied so that, when the primary model fails with a
retryable upstream error, the request is retried against the next model in the
chain. Fallback transitions are recorded through ``record_llm_fallback`` and
token usage through ``record_llm_token_usage`` (both in :mod:`app.metrics`).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.metrics import record_llm_fallback, record_llm_token_usage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider prefix mapping
# ---------------------------------------------------------------------------

#: Bare provider hint -> LiteLLM model prefix. LiteLLM routes to a provider by
#: prefixing the model name (e.g. ``gemini/gemini-2.0-flash``). When a caller
#: supplies a bare model without a prefix, we add the matching prefix here.
PROVIDER_PREFIX: dict[str, str] = {
    "openai": "openai",
    "google": "gemini",
    "gemini": "gemini",
    "anthropic": "anthropic",
    "claude": "anthropic",
}

#: Providers whose model names are *not* prefixed when passed bare to LiteLLM.
#: OpenAI models (``gpt-*``) work without the ``openai/`` prefix; keeping them
#: bare preserves the default routing behaviour used across the LiteLLM docs.
NO_PREFIX_PROVIDERS: frozenset[str] = frozenset({"openai"})

DEFAULT_TIMEOUT_S = 60.0


def resolve_litellm_model(model: str, provider: str | None) -> str:
    """Return a LiteLLM model string, adding a provider prefix when needed.

    If ``model`` already contains a ``/`` (e.g. ``anthropic/claude-3-5-sonnet``)
    it is returned unchanged — LiteLLM already knows how to route it.
    Otherwise the ``provider`` hint is used to pick the prefix; OpenAI models
    are returned bare because LiteLLM treats unprefixed models as OpenAI.
    """
    if "/" in model:
        return model
    if not provider:
        return model
    key = provider.strip().lower()
    if key in NO_PREFIX_PROVIDERS:
        return model
    prefix = PROVIDER_PREFIX.get(key)
    if prefix is None:
        raise ValueError(f"unsupported provider: {provider!r}")
    return f"{prefix}/{model}"


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single chat message in the request payload."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class LLMCompleteRequest(BaseModel):
    """Request body for ``POST /api/llm/complete``.

    Either ``model`` (optionally qualified with a provider prefix) or a
    ``model`` + ``provider`` pair must be supplied. ``fallback_models`` is an
    ordered list consulted only when the primary call fails with a retryable
    upstream error.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    provider: str | None = Field(
        default=None,
        description="Provider hint (openai|google|gemini|anthropic|claude) when 'model' is bare.",
    )
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    timeout: float | None = Field(default=None, gt=0.0)
    stream: bool = Field(default=False)
    fallback_models: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fallback_models")
    @classmethod
    def fallback_models_not_blank(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("fallback_models entries must not be blank")
        return value


class LLMCompleteResponse(BaseModel):
    """Normalized response returned by ``POST /api/llm/complete``."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str
    content: str
    role: str = "assistant"
    finish_reason: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    used_fallback: bool = False
    response_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# LiteLLM wrapper
# ---------------------------------------------------------------------------


class LLMRouter:
    """Thin async wrapper around :func:`litellm.acompletion`.

    Encapsulates model resolution, fallback handling and token/usage metric
    emission so the FastAPI route stays focused on HTTP concerns.
    """

    def __init__(
        self,
        *,
        default_timeout_s: float = DEFAULT_TIMEOUT_S,
        workspace_header: str = "x-workspace",
        user_header: str = "x-user",
    ) -> None:
        self.default_timeout_s = default_timeout_s
        self.workspace_header = workspace_header
        self.user_header = user_header

    async def complete(
        self,
        request: LLMCompleteRequest,
        *,
        workspace: str,
        user: str,
    ) -> LLMCompleteResponse:
        primary_model = resolve_litellm_model(request.model, request.provider)
        chain = [primary_model, *(resolve_litellm_model(m, request.provider) for m in request.fallback_models)]

        timeout = request.timeout or self.default_timeout_s
        litellm_kwargs: dict[str, Any] = {
            "messages": [msg.model_dump() for msg in request.messages],
            "temperature": request.temperature,
            "timeout": timeout,
            "stream": request.stream,
        }
        if request.max_tokens is not None:
            litellm_kwargs["max_tokens"] = request.max_tokens
        if request.metadata:
            litellm_kwargs["metadata"] = request.metadata

        last_exc: Exception | None = None
        used_fallback = False
        for index, resolved_model in enumerate(chain):
            if index > 0:
                record_llm_fallback(from_model=chain[index - 1], to_model=resolved_model)
                used_fallback = True
            try:
                response = await litellm.acompletion(model=resolved_model, **litellm_kwargs)
            except litellm.Timeout as exc:
                last_exc = exc
                logger.warning("litellm timeout for model=%s: %s", resolved_model, exc)
                continue
            except litellm.RateLimitError as exc:
                last_exc = exc
                logger.warning("litellm rate limit for model=%s: %s", resolved_model, exc)
                continue
            except litellm.ServiceUnavailableError as exc:
                last_exc = exc
                logger.warning("litellm service unavailable for model=%s: %s", resolved_model, exc)
                continue
            except litellm.APIConnectionError as exc:
                last_exc = exc
                logger.warning("litellm connection error for model=%s: %s", resolved_model, exc)
                continue
            # Non-retryable errors propagate immediately.
            return self._to_response(response, resolved_model, used_fallback, workspace=workspace, user=user)

        # Exhausted the chain — surface the last retryable error.
        assert last_exc is not None  # noqa: S101 — only reached when a retryable error occurred
        raise last_exc

    @staticmethod
    def _to_response(
        response: Any,
        resolved_model: str,
        used_fallback: bool,
        *,
        workspace: str,
        user: str,
    ) -> LLMCompleteResponse:
        """Normalize a LiteLLM ``ModelResponse`` into our schema + emit metrics."""
        choice = response.choices[0]
        message = choice.message
        content = message.content if isinstance(message.content, str) else str(message.content)
        finish_reason = getattr(choice, "finish_reason", None) or "stop"

        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)

        provider = resolved_model.split("/", 1)[0] if "/" in resolved_model else "openai"

        record_llm_token_usage(
            model=resolved_model,
            workspace=workspace,
            user=user,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        return LLMCompleteResponse(
            model=getattr(response, "model", resolved_model),
            provider=provider,
            content=content,
            role=getattr(message, "role", "assistant"),
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            used_fallback=used_fallback,
            response_id=getattr(response, "id", None),
            metadata={
                "resolved_model": resolved_model,
                **({"litellm_hidden_params": dict(response.get("hidden_params", {}))} if hasattr(response, "get") else {}),
            },
        )


# ---------------------------------------------------------------------------
# Router / endpoint
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/llm", tags=["llm"])
_router_instance = LLMRouter()


def _consumer_headers(headers: Any) -> tuple[str, str]:
    workspace = headers.get(_router_instance.workspace_header, "default") or "default"
    user = headers.get(_router_instance.user_header, "anonymous") or "anonymous"
    return workspace, user


@router.post(
    "/complete",
    response_model=LLMCompleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete a chat prompt via an agnostic LLM provider.",
)
async def complete(request: LLMCompleteRequest) -> LLMCompleteResponse:
    """Route a completion request to OpenAI, Google or Anthropic via LiteLLM.

    The provider is derived from the model string's LiteLLM prefix
    (``anthropic/...``, ``gemini/...``) or, when absent, from the optional
    ``provider`` field. A ``fallback_models`` chain is consulted on retryable
    upstream failures (timeout, rate limit, connection, service unavailable).
    """
    # FastAPI injects the Request via dependency below; this wrapper keeps the
    # signature clean for the OpenAPI schema while still reading consumer
    # headers for token attribution.
    return await _handle_complete(request)


from fastapi import Request as _FastAPIRequest  # noqa: E402


async def _handle_complete(request: LLMCompleteRequest, fastapi_request: _FastAPIRequest | None = None) -> LLMCompleteResponse:
    if fastapi_request is None:
        workspace, user = "default", "anonymous"
    else:
        workspace, user = _consumer_headers(fastapi_request.headers)
    try:
        return await _router_instance.complete(request, workspace=workspace, user=user)
    except litellm.AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "provider_auth_error", "message": str(exc)},
        ) from exc
    except litellm.BadRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "provider_bad_request", "message": str(exc)},
        ) from exc
    except litellm.NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "model_not_found", "message": str(exc)},
        ) from exc
    except litellm.ContextWindowExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "context_window_exceeded", "message": str(exc)},
        ) from exc
    except litellm.ContentPolicyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "content_policy_violation", "message": str(exc)},
        ) from exc
    except litellm.PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "permission_denied", "message": str(exc)},
        ) from exc
    except (litellm.Timeout, litellm.RateLimitError, litellm.ServiceUnavailableError, litellm.APIConnectionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "provider_unavailable",
                "message": "All models in the chain failed with retryable errors.",
                "last_error": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_request", "message": str(exc)},
        ) from exc
    except litellm.APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "provider_error", "message": str(exc)},
        ) from exc


# Re-bind the route so the consumer headers are actually read from the request.
# FastAPI only injects parameters that appear in the signature, so we replace
# the placeholder ``complete`` dependency with one that receives the Request.
async def _complete_with_request(
    request: LLMCompleteRequest,
    fastapi_request: _FastAPIRequest,
) -> LLMCompleteResponse:
    return await _handle_complete(request, fastapi_request)


# Overwrite the route handler registered above so the dependency is wired.
router.routes.clear()


@router.post(
    "/complete",
    response_model=LLMCompleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete a chat prompt via an agnostic LLM provider.",
)
async def complete(  # noqa: F811 — intentional redefinition to bind Request dependency
    request: LLMCompleteRequest,
    fastapi_request: _FastAPIRequest,
) -> LLMCompleteResponse:
    return await _complete_with_request(request, fastapi_request)


# ---------------------------------------------------------------------------
# Provider discovery helper
# ---------------------------------------------------------------------------


@router.get(
    "/providers",
    summary="List supported LLM providers and their LiteLLM model prefixes.",
)
def list_providers() -> dict[str, dict[str, str]]:
    """Return the provider hint -> LiteLLM prefix mapping used for resolution."""
    configured: dict[str, bool] = {}
    for env_name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        configured[env_name] = bool(os.environ.get(env_name))
    return {
        "providers": {
            "openai": {"prefix": "openai", "env_key": "OPENAI_API_KEY"},
            "google": {"prefix": "gemini", "env_key": "GEMINI_API_KEY"},
            "gemini": {"prefix": "gemini", "env_key": "GEMINI_API_KEY"},
            "anthropic": {"prefix": "anthropic", "env_key": "ANTHROPIC_API_KEY"},
            "claude": {"prefix": "anthropic", "env_key": "ANTHROPIC_API_KEY"},
        },
        "configured": configured,
    }

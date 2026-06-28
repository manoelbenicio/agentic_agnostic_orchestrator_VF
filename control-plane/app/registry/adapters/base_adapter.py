"""
Base adapter contract for the AOP LLM registry.

This module defines the abstract `BaseAdapter` interface that all provider
adapters (Google, Azure OpenAI, Anthropic, Ollama, etc.) must implement. It
also defines the shared value types exchanged with the rest of the registry:

    * `HealthStatus`  - coarse-grained provider health state.
    * `ModelInfo`     - metadata about a model exposed by a provider.
    * `CompletionResult` - normalized result of a non-streaming completion.
    * `BaseAdapter`   - ABC that every concrete adapter subclasses.

The contract intentionally stays narrow: it only specifies the methods every
adapter MUST expose, not the per-provider knobs that callers may pass through
`complete` / `stream` / `initialize` (those are surfaced as `**kwargs` and
provider-specific config mappings).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared value types
# ---------------------------------------------------------------------------


class HealthStatus(str, Enum):
    """Coarse-grained health state of an upstream provider.

    Kept intentionally simple and provider-agnostic so that adapters can map
    their native health semantics onto it. Values mirror the topology
    `HealthStatus` enum for consistency, but the two enums are deliberately
    distinct types: provider reachability is not the same as topology-agent
    liveness.
    """

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


class ModelInfo(BaseModel):
    """Provider-agnostic description of a single model."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Provider-native model identifier.")
    name: str = Field(..., description="Human-readable display name.")
    provider: str = Field(..., description="Provider key (e.g. 'google', 'azure_openai').")
    context_window: Optional[int] = Field(
        default=None, description="Maximum input context length in tokens."
    )
    max_output_tokens: Optional[int] = Field(
        default=None, description="Maximum output tokens the model can produce."
    )
    supports_streaming: bool = Field(default=True, description="Whether the model supports streaming.")
    supports_vision: bool = Field(default=False, description="Whether the model accepts image inputs.")
    input_cost_per_1k: Optional[float] = Field(
        default=None, description="USD per 1,000 input tokens (None = unknown).",
    )
    output_cost_per_1k: Optional[float] = Field(
        default=None, description="USD per 1,000 output tokens (None = unknown).",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Free-form provider-specific metadata.",
    )


class CompletionResult(BaseModel):
    """Normalized result of a non-streaming chat completion."""

    model_config = ConfigDict(extra="allow")

    content: str = Field(..., description="Assistant message text returned by the model.")
    model: str = Field(..., description="Model identifier that produced the result.")
    provider: str = Field(..., description="Provider key that produced the result.")
    prompt_tokens: Optional[int] = Field(default=None, description="Input tokens consumed.")
    completion_tokens: Optional[int] = Field(default=None, description="Output tokens produced.")
    total_tokens: Optional[int] = Field(default=None, description="Total tokens consumed (input + output).")
    finish_reason: Optional[str] = Field(
        default=None, description="Provider-supplied finish reason (e.g. 'stop', 'length').",
    )
    cost: Optional[float] = Field(default=None, description="Estimated USD cost of this completion.")
    raw: Optional[Dict[str, Any]] = Field(
        default=None, description="Unmodified provider response (for debugging / advanced use).",
    )


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class BaseAdapter(ABC):
    """Abstract base class for every LLM provider adapter.

    Lifecycle
    ---------
    Adapters are constructed with no arguments, then handed a config mapping
    via :meth:`initialize`. This split lets the registry instantiate adapters
    generically (e.g. via reflection) and configure them later once their
    target deployment / region / credentials are known.

    Method contracts
    ----------------
    All I/O-bearing methods are coroutines so they integrate cleanly with the
    rest of the FastAPI/async registry code. The only sync method is
    :meth:`initialize`, which should be cheap and side-effect-only (open
    clients, validate config, etc.) — it must NOT perform network I/O.

    `stream` returns an `AsyncGenerator[str, None]` that yields raw text deltas
    (assistant message fragments) in arrival order. Callers that want a final
    aggregated `CompletionResult` must collect deltas and assemble it
    themselves; providers that natively return chunked `CompletionResult`-like
    objects should reduce them to text before yielding.
    """

    #: Class-level provider key. Concrete adapters MUST override this.
    provider_name: str = "base"

    def __init__(self) -> None:
        self._initialized: bool = False
        self._config: Dict[str, Any] = {}

    # ------------------------------------------------------------------ init

    @abstractmethod
    def initialize(self, config: Mapping[str, Any]) -> None:
        """Configure the adapter from a provider-specific config mapping.

        Implementations should validate required keys, build clients, and
        store any derived state on `self`. They MUST NOT perform network I/O.
        Implementations MUST set `self._initialized = True` on success and
        raise (without touching the flag) on invalid config.
        """
        raise NotImplementedError

    # ----------------------------------------------------------- I/O surface

    @abstractmethod
    async def complete(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> CompletionResult:
        """Execute a non-streaming chat completion.

        Parameters
        ----------
        model:
            Provider-native model identifier (e.g. ``"gemini-2.5-pro"`` or an
            Azure deployment name).
        messages:
            OpenAI-style chat history, each entry ``{"role": ..., "content": ...}``.
        **kwargs:
            Provider-specific options (temperature, max_tokens, tools, ...).
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Execute a streaming chat completion, yielding text deltas.

        Must be implemented as an async generator. Implementations should
        translate provider-native chunk types into plain text fragments before
        yielding, so callers can concatenate them to reconstruct the assistant
        message.
        """
        raise NotImplementedError
        yield ""  # pragma: no cover - makes this function an async generator for type-checkers

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """Return metadata for every model the adapter can dispatch to."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Probe the upstream provider and return its current health.

        Implementations should map transient errors to ``DEGRADED`` and
        connection-level failures to ``UNREACHABLE``; only return ``HEALTHY``
        when an authenticated round-trip succeeds.
        """
        raise NotImplementedError

    @abstractmethod
    async def estimate_cost(
        self,
        model: str,
        messages: List[Dict[str, Any]],
    ) -> float:
        """Return a USD cost estimate for running ``complete`` on `messages`.

        Implementations may use a fast heuristic (token count * price table)
        rather than waiting for a real completion. Returning ``0.0`` is a
        valid answer for free / locally hosted models.
        """
        raise NotImplementedError

    # ------------------------------------------------------------ introspection

    @property
    def is_initialized(self) -> bool:
        """True once :meth:`initialize` has completed successfully."""
        return self._initialized

    @property
    def config(self) -> Mapping[str, Any]:
        """Read-only view of the config passed to :meth:`initialize`."""
        # Return a shallow copy so callers can't mutate adapter state.
        return dict(self._config)

    def _mark_initialized(self, config: Mapping[str, Any]) -> None:
        """Helper for subclasses: store config + flip the initialized flag."""
        self._config = dict(config)
        self._initialized = True

"""
LLM provider adapters for the AOP control plane.

This package provides a pluggable adapter framework that lets the registry
dispatch chat-completion requests to any supported LLM provider behind a
single ``BaseAdapter`` interface.

Public surface
--------------
Concrete adapters
    * :class:`GoogleAdapter`      — Google Gemini 2.5 Pro / Flash (google-genai SDK).
    * :class:`AzureOpenAIAdapter` — Azure OpenAI Service (openai SDK, AsyncAzureOpenAI).
    * :class:`OllamaAdapter`      — Local Ollama instance (REST). Pre-dates
      :class:`BaseAdapter`; structurally compatible but not a subclass.

Shared value types
    * :class:`BaseAdapter`      — abstract base every conforming adapter subclasses.
    * :class:`CompletionResult` — normalized non-streaming result type.
    * :class:`ModelInfo`        — normalized model descriptor type.
    * :class:`HealthStatus`     — coarse-grained provider health enum.

Factory
-------
:func:`create_adapter` is a thin factory that instantiates (and optionally
initializes) an adapter by provider key. :data:`PROVIDER_REGISTRY` maps
provider keys to adapter classes for callers that want to iterate or
register them dynamically.

Note
----
The Ollama adapter is exported for backward compatibility but is not listed
in ``PROVIDER_REGISTRY`` because its lifecycle differs from
``BaseAdapter`` (it takes ``base_url`` in ``__init__`` rather than a config
mapping in ``initialize``). Migrating it to subclass ``BaseAdapter`` is a
separate task.
"""

from .base_adapter import (
    BaseAdapter,
    CompletionResult,
    HealthStatus,
    ModelInfo,
)
from .google_adapter import GoogleAdapter
from .azure_adapter import AzureOpenAIAdapter
from .ollama_adapter import OllamaAdapter

# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

__all__ = [
    # Abstract contract
    "BaseAdapter",
    "CompletionResult",
    "HealthStatus",
    "ModelInfo",
    # Concrete adapters
    "GoogleAdapter",
    "AzureOpenAIAdapter",
    "OllamaAdapter",
    # Factory helpers
    "create_adapter",
    "PROVIDER_REGISTRY",
]


# ---------------------------------------------------------------------------
# Provider registry + factory
# ---------------------------------------------------------------------------

#: Mapping of provider key -> adapter class for adapters that conform to the
#: :class:`BaseAdapter` lifecycle (no-arg ``__init__`` + ``initialize(config)``).
PROVIDER_REGISTRY: dict = {
    "google": GoogleAdapter,
    "azure_openai": AzureOpenAIAdapter,
}


def create_adapter(provider: str, config=None):
    """Instantiate (and optionally initialize) an adapter by provider name.

    Parameters
    ----------
    provider:
        One of the keys in :data:`PROVIDER_REGISTRY` (e.g. ``"google"``,
        ``"azure_openai"``).
    config:
        Optional provider-specific config mapping passed to
        :meth:`BaseAdapter.initialize`. If ``None``, the adapter is returned
        uninitialized and the caller is responsible for invoking
        ``initialize`` before use.

    Returns
    -------
    BaseAdapter
        An adapter instance — initialized if ``config`` was supplied,
        uninitialized otherwise.

    Raises
    ------
    KeyError
        If ``provider`` is not registered in :data:`PROVIDER_REGISTRY`.
    RuntimeError, ValueError
        Propagated from ``initialize`` when the SDK is missing or the
        config is invalid.
    """
    cls = PROVIDER_REGISTRY.get(provider)
    if cls is None:
        raise KeyError(
            f"Unknown adapter provider '{provider}'. Registered providers: "
            f"{sorted(PROVIDER_REGISTRY)}"
        )
    adapter = cls()
    if config is not None:
        adapter.initialize(config)
    return adapter

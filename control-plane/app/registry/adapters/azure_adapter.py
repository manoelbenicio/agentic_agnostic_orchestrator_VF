"""
Azure OpenAI adapter for the AOP LLM registry.

Implements the `BaseAdapter` contract on top of the official ``openai`` SDK's
``AsyncAzureOpenAI`` client. Targets Azure OpenAI Service deployments of
OpenAI / o-series models.

SDK notes
---------
Azure OpenAI does not expose a public, OpenAI-SDK-compatible list-deployments
endpoint on the data plane. Deployments are therefore declared statically via
the adapter config (``deployments`` and/or ``deployment_name``). The
``health_check`` still attempts a live ``/models`` round-trip; when that
endpoint is unavailable (it is on some Azure regions / SKUs) it falls back
to a config-based health verdict.

Pricing
-------
Azure does not publish per-deployment prices via the SDK; operators must
populate ``input_cost_per_1k`` / ``output_cost_per_1k`` per deployment in the
config (USD). When unset, ``estimate_cost`` and the per-completion cost
field return ``0.0``.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Mapping, Optional

from .base_adapter import BaseAdapter, CompletionResult, HealthStatus, ModelInfo

logger = logging.getLogger("registry.adapters.azure_openai")

# ---------------------------------------------------------------------------
# Optional SDK import — keep module importable even when openai is not
# installed. Adapter construction succeeds; initialization fails with a clear
# error message instead.
# ---------------------------------------------------------------------------

try:  # pragma: no cover - exercised only when SDK is present
    from openai import AsyncAzureOpenAI as _AsyncAzureOpenAI  # type: ignore[import-untyped]
    from openai import APIConnectionError as _APIConnectionError  # type: ignore[import-untyped]
    from openai import AuthenticationError as _AuthenticationError  # type: ignore[import-untyped]
    from openai import BadRequestError as _BadRequestError  # type: ignore[import-untyped]
    from openai import NotFoundError as _NotFoundError  # type: ignore[import-untyped]

    _OPENAI_AVAILABLE = True
    _OPENAI_IMPORT_ERROR: Optional[Exception] = None
except Exception as _exc:  # pragma: no cover - exercised only when SDK missing
    _AsyncAzureOpenAI = None  # type: ignore[assignment]
    _APIConnectionError = None  # type: ignore[assignment]
    _AuthenticationError = None  # type: ignore[assignment]
    _BadRequestError = None  # type: ignore[assignment]
    _NotFoundError = None  # type: ignore[assignment]
    _OPENAI_AVAILABLE = False
    _OPENAI_IMPORT_ERROR = _exc


_DEFAULT_API_VERSION = "2024-08-01-preview"


class AzureOpenAIAdapter(BaseAdapter):
    """Adapter for Azure OpenAI Service via the openai SDK.

    Configuration
    -------------
    Minimum required keys::

        AzureOpenAIAdapter().initialize({
            "api_key":        "...",                                  # or `azure_ad_token`
            "azure_endpoint": "https://<resource>.openai.azure.com/",
            "api_version":    "2024-08-01-preview",                   # optional
            "deployment_name": "my-gpt4o-deployment",                 # optional default
        })

    Listing deployments
    ~~~~~~~~~~~~~~~~~~~
    Azure has no data-plane "list deployments" endpoint, so deployments must
    be declared in config. Either::

        "deployment_name": "my-gpt4o"     # single deployment shorthand

    or::

        "deployments": [
            {"deployment_name": "my-gpt4o",
             "model":              "gpt-4o",
             "display_name":       "GPT-4o (prod)",
             "context_window":     128000,
             "max_output_tokens":  4096,
             "input_cost_per_1k":  0.005,
             "output_cost_per_1k": 0.015},
            {"deployment_name": "my-embed",
             "model":              "text-embedding-3-large"},
        ]

    Optional keys
    ~~~~~~~~~~~~~
    - ``timeout``     - HTTP timeout in seconds (float).
    - ``max_retries`` - SDK-managed retry count (int).
    - ``azure_ad_token`` - alternate to ``api_key`` for AAD/managed identity.
    """

    provider_name = "azure_openai"

    def __init__(self) -> None:
        super().__init__()
        self._client: Optional[Any] = None  # _AsyncAzureOpenAI
        self._deployments: List[Any] = []
        self._default_deployment: Optional[str] = None

    # ------------------------------------------------------------------ init

    def initialize(self, config: Mapping[str, Any]) -> None:
        if not _OPENAI_AVAILABLE:
            raise RuntimeError(
                "openai SDK is not installed. Install it with "
                "`pip install openai` and retry."
            ) from _OPENAI_IMPORT_ERROR

        api_key = config.get("api_key") or config.get("azure_ad_token")
        if not api_key:
            raise ValueError(
                "AzureOpenAIAdapter requires `api_key` (or `azure_ad_token` "
                "for AAD / managed-identity auth)."
            )

        azure_endpoint = config.get("azure_endpoint")
        if not azure_endpoint:
            raise ValueError(
                "AzureOpenAIAdapter requires `azure_endpoint`, e.g. "
                "'https://<resource>.openai.azure.com/'."
            )
        api_version = str(config.get("api_version") or _DEFAULT_API_VERSION)

        client_kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "azure_endpoint": str(azure_endpoint).rstrip("/"),
            "api_version": api_version,
        }
        if "timeout" in config and config["timeout"] is not None:
            client_kwargs["timeout"] = float(config["timeout"])
        if "max_retries" in config and config["max_retries"] is not None:
            client_kwargs["max_retries"] = int(config["max_retries"])

        try:
            self._client = _AsyncAzureOpenAI(**client_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to construct AsyncAzureOpenAI client: {e}"
            ) from e

        # Persist deployment descriptors for list_models().
        deployments_cfg = config.get("deployments") or []
        if not isinstance(deployments_cfg, list):
            raise ValueError("`deployments` config must be a list of deployment descriptors.")
        self._deployments = deployments_cfg

        default_deployment = config.get("deployment_name")
        if default_deployment:
            self._default_deployment = str(default_deployment)

        self._mark_initialized(config)
        logger.info(
            "AzureOpenAIAdapter initialized (endpoint=%s, api_version=%s, deployments=%d)",
            azure_endpoint,
            api_version,
            len(self._deployments),
        )

    # ----------------------------------------------------------- I/O surface

    async def complete(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> CompletionResult:
        client = self._require_client()
        deployment = self._resolve_deployment(model)
        request_kwargs = self._build_request_kwargs(kwargs)

        try:
            response = await client.chat.completions.create(
                model=deployment,
                messages=messages,
                **request_kwargs,
            )
        except Exception as e:
            raise self._translate_error(deployment, e) from e

        usage = self._extract_usage(response)
        cost = self._compute_cost(
            deployment,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

        return CompletionResult(
            content=self._extract_text(response),
            model=deployment,
            provider=self.provider_name,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            finish_reason=self._extract_finish_reason(response),
            cost=cost,
            raw=self._response_to_raw(response),
        )

    async def stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        client = self._require_client()
        deployment = self._resolve_deployment(model)
        request_kwargs = self._build_request_kwargs(kwargs)
        request_kwargs["stream"] = True

        try:
            stream_obj = await client.chat.completions.create(
                model=deployment,
                messages=messages,
                **request_kwargs,
            )
        except Exception as e:
            raise self._translate_error(deployment, e) from e

        async for chunk in stream_obj:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text

    async def list_models(self) -> List[ModelInfo]:
        out: List[ModelInfo] = []
        for d in self._deployments:
            info = self._deployment_to_model_info(d)
            if info is not None:
                out.append(info)
        return out

    async def health_check(self) -> HealthStatus:
        if not self._initialized or self._client is None:
            return HealthStatus.UNKNOWN

        # Attempt a live data-plane probe first.
        try:
            pager = await self._client.models.list()
            async for _ in pager:  # force at least one round-trip
                break
            return HealthStatus.HEALTHY
        except Exception as e:
            translated = self._translate_error("", e)
            # NotFoundError on /models is expected on many Azure SKUs — not a
            # real outage. Fall through to config-based verdict in that case.
            if isinstance(translated, ValueError) and "/models" in str(translated):
                logger.debug("Azure /models endpoint unavailable; using config-based health")
            elif isinstance(translated, PermissionError):
                return HealthStatus.UNREACHABLE
            elif isinstance(translated, ConnectionError):
                return HealthStatus.UNREACHABLE
            elif isinstance(translated, _BadRequestError) if _BadRequestError else False:
                return HealthStatus.DEGRADED
            else:
                # Unknown error — be conservative.
                logger.warning("AzureOpenAIAdapter health check error: %s", e)
                return HealthStatus.DEGRADED

        # Fallback: if at least one deployment is configured, trust the config.
        if self._deployments or self._default_deployment:
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN

    async def estimate_cost(
        self,
        model: str,
        messages: List[Dict[str, Any]],
    ) -> float:
        deployment = self._resolve_deployment(model)
        pricing = self._get_deployment_pricing(deployment)
        if not pricing:
            return 0.0
        # Cheap char/4 heuristic — issuing a real call to learn token counts
        # would itself incur cost.
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        prompt_tokens = max(1, total_chars // 4)
        input_cost = pricing.get("input_per_1k", 0.0) * prompt_tokens / 1000.0
        return round(input_cost, 6)

    # ------------------------------------------------------------- internals

    def _require_client(self) -> Any:
        if not self._initialized or self._client is None:
            raise RuntimeError("AzureOpenAIAdapter.initialize() must be called first.")
        return self._client

    def _resolve_deployment(self, model: Optional[str]) -> str:
        """Resolve the Azure deployment name to use for a request.

        In Azure OpenAI the ``model=`` parameter on the chat API is the
        *deployment name* (not the underlying model name like ``gpt-4o``).
        Order of precedence:

        1. ``model`` argument passed by the caller.
        2. ``deployment_name`` from the adapter config.
        3. First entry in ``deployments`` from the adapter config.
        """
        if model:
            return model
        if self._default_deployment:
            return self._default_deployment
        if self._deployments:
            first = self._deployments[0]
            name: Optional[str] = None
            if isinstance(first, Mapping):
                name = first.get("deployment_name") or first.get("name")  # type: ignore[union-attr]
            elif isinstance(first, str):
                name = first
            if name:
                return str(name)
        raise ValueError(
            "AzureOpenAIAdapter has no deployment_name configured and no `model` "
            "argument was passed."
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        msg = getattr(choices[0], "message", None)
        if msg is None:
            return ""
        return getattr(msg, "content", "") or ""

    @staticmethod
    def _extract_usage(response: Any) -> Dict[str, Optional[int]]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @staticmethod
    def _extract_finish_reason(response: Any) -> Optional[str]:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        reason = getattr(choices[0], "finish_reason", None)
        return str(reason) if reason is not None else None

    @staticmethod
    def _response_to_raw(response: Any) -> Optional[Dict[str, Any]]:
        for method in ("model_dump", "to_dict"):
            fn = getattr(response, method, None)
            if fn is None:
                continue
            try:
                dumped = fn()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:  # pragma: no cover - SDK-dependent
                continue
        return None

    def _build_request_kwargs(self, kwargs: Mapping[str, Any]) -> Dict[str, Any]:
        """Translate generic kwargs into ``chat.completions.create`` kwargs."""
        out: Dict[str, Any] = {}
        if kwargs.get("temperature") is not None:
            out["temperature"] = float(kwargs["temperature"])
        if kwargs.get("max_tokens") is not None:
            out["max_tokens"] = int(kwargs["max_tokens"])
        if kwargs.get("top_p") is not None:
            out["top_p"] = float(kwargs["top_p"])
        if kwargs.get("frequency_penalty") is not None:
            out["frequency_penalty"] = float(kwargs["frequency_penalty"])
        if kwargs.get("presence_penalty") is not None:
            out["presence_penalty"] = float(kwargs["presence_penalty"])
        stop = kwargs.get("stop")
        if stop:
            out["stop"] = list(stop) if isinstance(stop, (list, tuple)) else stop
        if kwargs.get("tools"):
            out["tools"] = kwargs["tools"]
        if "tool_choice" in kwargs and kwargs["tool_choice"] is not None:
            out["tool_choice"] = kwargs["tool_choice"]
        if kwargs.get("response_format") is not None:
            out["response_format"] = kwargs["response_format"]
        if kwargs.get("seed") is not None:
            out["seed"] = int(kwargs["seed"])
        if kwargs.get("user"):
            out["user"] = str(kwargs["user"])
        return out

    def _deployment_to_model_info(self, d: Any) -> Optional[ModelInfo]:
        if isinstance(d, str):
            return ModelInfo(
                id=d,
                name=d,
                provider=self.provider_name,
                supports_streaming=True,
            )
        if isinstance(d, Mapping):
            deployment_name = d.get("deployment_name") or d.get("name")
            if not deployment_name:
                return None
            model_name = d.get("model") or d.get("model_name") or deployment_name
            return ModelInfo(
                id=str(deployment_name),
                name=str(d.get("display_name") or model_name),
                provider=self.provider_name,
                context_window=d.get("context_window"),
                max_output_tokens=d.get("max_output_tokens"),
                supports_streaming=bool(d.get("supports_streaming", True)),
                supports_vision=bool(d.get("supports_vision", False)),
                input_cost_per_1k=d.get("input_cost_per_1k"),
                output_cost_per_1k=d.get("output_cost_per_1k"),
                metadata={"underlying_model": model_name},
            )
        return None

    def _get_deployment_pricing(self, deployment_name: str) -> Dict[str, float]:
        for d in self._deployments:
            if not isinstance(d, Mapping):
                continue
            name = d.get("deployment_name") or d.get("name")
            if name == deployment_name:
                result: Dict[str, float] = {}
                if d.get("input_cost_per_1k") is not None:
                    result["input_per_1k"] = float(d["input_cost_per_1k"])
                if d.get("output_cost_per_1k") is not None:
                    result["output_per_1k"] = float(d["output_cost_per_1k"])
                return result
        return {}

    def _compute_cost(
        self,
        deployment_name: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        pricing = self._get_deployment_pricing(deployment_name)
        if not pricing:
            return 0.0
        input_cost = pricing.get("input_per_1k", 0.0) * prompt_tokens / 1000.0
        output_cost = pricing.get("output_per_1k", 0.0) * completion_tokens / 1000.0
        return round(input_cost + output_cost, 6)

    @staticmethod
    def _translate_error(deployment: str, exc: Exception) -> Exception:
        # Order matters: most specific first.
        if _NotFoundError is not None and isinstance(exc, _NotFoundError):
            if deployment:
                return ValueError(f"Deployment not found on Azure OpenAI: {deployment}")
            return ValueError("Azure OpenAI endpoint not found (/models unavailable)")
        if _AuthenticationError is not None and isinstance(exc, _AuthenticationError):
            return PermissionError(f"Azure OpenAI authentication failed: {exc}")
        if _APIConnectionError is not None and isinstance(exc, _APIConnectionError):
            return ConnectionError(f"Azure OpenAI connection error: {exc}")
        if _BadRequestError is not None and isinstance(exc, _BadRequestError):
            # Re-raise as ValueError — caller likely supplied a bad arg.
            return ValueError(f"Azure OpenAI rejected request: {exc}")
        return exc

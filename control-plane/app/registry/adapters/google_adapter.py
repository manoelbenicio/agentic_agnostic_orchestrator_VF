"""
Google Gemini adapter for the AOP LLM registry.

Implements the `BaseAdapter` contract on top of the unified `google-genai`
SDK (https://pypi.org/project/google-genai/). The adapter targets the Gemini
2.5 generation of models (Pro and Flash) and supports both the Gemini
Developer API (API key) and Vertex AI (project + location) deployment modes.

SDK notes
---------
The new unified SDK exposes both a sync client (`client.models`) and an async
client (`client.aio.models`). All I/O in this adapter goes through the async
client so it composes cleanly with the rest of the FastAPI/async registry.

Pricing
-------
`cost_overrides` in the config can fully replace the bundled price table.
Defaults reflect Google's publicly-listed Gemini 2.5 rates at the time of
writing and should be re-validated whenever Google revises them.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Mapping, Optional, Tuple

from .base_adapter import BaseAdapter, CompletionResult, HealthStatus, ModelInfo

logger = logging.getLogger("registry.adapters.google")

# ---------------------------------------------------------------------------
# Optional SDK import — keep module importable even when google-genai is not
# installed. Adapter construction succeeds; initialization fails with a clear
# error message instead.
# ---------------------------------------------------------------------------

try:  # pragma: no cover - exercised only when SDK is present
    from google import genai as _genai  # type: ignore[import-untyped]
    from google.genai import types as _genai_types  # type: ignore[import-untyped]

    _GENAI_AVAILABLE = True
    _GENAI_IMPORT_ERROR: Optional[Exception] = None
except Exception as _exc:  # pragma: no cover - exercised only when SDK missing
    _genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]
    _GENAI_AVAILABLE = False
    _GENAI_IMPORT_ERROR = _exc


# Bundled price table: USD per 1M tokens. Keep these as conservative defaults;
# operators can override via config["cost_overrides"].
_DEFAULT_PRICING_PER_MILLION: Dict[str, Dict[str, float]] = {
    "gemini-2.5-pro": {
        "input_per_1m": 1.25,
        "output_per_1m": 10.0,
    },
    "gemini-2.5-flash": {
        "input_per_1m": 0.075,
        "output_per_1m": 0.30,
    },
}

# Role names we accept on the OpenAI-style message dict.
_ROLE_MAP = {
    "user": "user",
    "assistant": "model",
    "model": "model",
    "system": "system",  # handled separately as a system instruction
}


class GoogleAdapter(BaseAdapter):
    """Adapter for Google Gemini (Gemini 2.5 Pro / 2.5 Flash) via google-genai.

    Configuration
    -------------
    For Gemini Developer API::

        GoogleAdapter().initialize({
            "api_key": "AIza...",
        })

    For Vertex AI::

        GoogleAdapter().initialize({
            "vertexai": True,
            "project": "my-gcp-project",
            "location": "us-central1",   # optional, defaults to us-central1
        })

    Optional keys
    ~~~~~~~~~~~~~
    ``cost_overrides`` - mapping of ``model_id`` -> ``{"input_per_1m": float,
    "output_per_1m": float}`` to override the bundled price table.
    """

    provider_name = "google"

    #: Models this adapter is allowed to dispatch to. Used to validate
    #: ``model`` parameters against typos before the SDK raises an opaque error.
    SUPPORTED_MODEL_PREFIXES = ("gemini-2.5-pro", "gemini-2.5-flash")

    def __init__(self) -> None:
        super().__init__()
        self._client: Optional[Any] = None
        # Per-instance price table (USD per 1M tokens) seeded from defaults.
        self._pricing: Dict[str, Dict[str, float]] = {
            model: dict(prices) for model, prices in _DEFAULT_PRICING_PER_MILLION.items()
        }

    # ------------------------------------------------------------------ init

    def initialize(self, config: Mapping[str, Any]) -> None:
        if not _GENAI_AVAILABLE:
            raise RuntimeError(
                "google-genai SDK is not installed. Install it with "
                "`pip install google-genai` and retry."
            ) from _GENAI_IMPORT_ERROR

        api_key = config.get("api_key")
        use_vertex = bool(config.get("vertexai"))

        if not api_key and not use_vertex:
            raise ValueError(
                "GoogleAdapter config requires either `api_key` (Gemini "
                "Developer API) or `vertexai=True` plus `project` (Vertex AI)."
            )

        client_kwargs: Dict[str, Any] = {}
        if use_vertex:
            project = config.get("project")
            if not project:
                raise ValueError("GoogleAdapter Vertex AI config requires `project`.")
            client_kwargs["vertexai"] = True
            client_kwargs["project"] = project
            client_kwargs["location"] = config.get("location", "us-central1")
            if api_key:
                # Optional: pass through for APIs that still need a key on Vertex.
                client_kwargs["api_key"] = api_key
        else:
            client_kwargs["api_key"] = api_key

        try:
            self._client = _genai.Client(**client_kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to construct google-genai client: {e}") from e

        # Apply pricing overrides (per-1M-token rates).
        cost_overrides = config.get("cost_overrides") or {}
        if not isinstance(cost_overrides, Mapping):
            raise ValueError("`cost_overrides` must be a mapping of model_id -> price dict.")
        for model_name, prices in cost_overrides.items():
            if not isinstance(prices, Mapping):
                raise ValueError(
                    f"`cost_overrides[{model_name}]` must be a mapping of "
                    f"price keys -> float values."
                )
            slot = self._pricing.setdefault(model_name, {})
            slot.update({k: float(v) for k, v in prices.items()})

        self._mark_initialized(config)
        logger.info(
            "GoogleAdapter initialized (mode=%s, models=%d)",
            "vertex" if use_vertex else "api_key",
            len(self._pricing),
        )

    # ----------------------------------------------------------- conversion

    @staticmethod
    def _convert_messages(
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[Any], Optional[str]]:
        """Translate OpenAI-style chat messages to google-genai contents.

        Returns ``(contents, system_instruction)``. System messages are
        collapsed into a single system instruction (last one wins) because
        Gemini accepts only one ``system_instruction`` per request.
        """
        contents: List[Any] = []
        system_instruction: Optional[str] = None

        for msg in messages:
            role = _ROLE_MAP.get(msg.get("role", "user"), "user")
            content = msg.get("content", "")
            text = content if isinstance(content, str) else str(content)

            if role == "system":
                system_instruction = text
                continue

            contents.append({"role": role, "parts": [{"text": text}]})

        return contents, system_instruction

    def _build_generation_config(
        self,
        system_instruction: Optional[str],
        kwargs: Mapping[str, Any],
    ) -> Optional[Any]:
        """Build a ``GenerateContentConfig`` from known kwargs (best-effort)."""
        if _genai_types is None:  # pragma: no cover - guarded by initialize()
            return None

        cfg: Dict[str, Any] = {}
        if system_instruction:
            cfg["system_instruction"] = system_instruction
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            cfg["temperature"] = float(kwargs["temperature"])
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            cfg["max_output_tokens"] = int(kwargs["max_tokens"])
        if "top_p" in kwargs and kwargs["top_p"] is not None:
            cfg["top_p"] = float(kwargs["top_p"])
        if "top_k" in kwargs and kwargs["top_k"] is not None:
            cfg["top_k"] = int(kwargs["top_k"])
        if "stop" in kwargs and kwargs["stop"]:
            cfg["stop_sequences"] = list(kwargs["stop"])

        if not cfg:
            return None
        return _genai_types.GenerateContentConfig(**cfg)

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull concatenated text from a google-genai response or chunk."""
        # New SDK exposes a convenience `.text` accessor on responses and on
        # many streaming chunks. Guard it because some chunks legitimately
        # contain no text (e.g. function-call-only chunks).
        try:
            text = getattr(response, "text", None)
            if text:
                return text
        except Exception:  # pragma: no cover - SDK-level guard
            pass

        chunks: List[str] = []
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            if content is None:
                continue
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if t:
                    chunks.append(t)
        return "".join(chunks)

    @staticmethod
    def _extract_usage(response: Any) -> Dict[str, Optional[int]]:
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        return {
            "prompt_tokens": getattr(meta, "prompt_token_count", None),
            "completion_tokens": getattr(meta, "candidates_token_count", None),
            "total_tokens": getattr(meta, "total_token_count", None),
        }

    @staticmethod
    def _extract_finish_reason(response: Any) -> Optional[str]:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        reason = getattr(candidates[0], "finish_reason", None)
        if reason is None:
            return None
        # Enum-like values stringify cleanly.
        return str(reason)

    def _response_to_raw(self, response: Any) -> Optional[Dict[str, Any]]:
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

    def _require_client(self) -> Any:
        if not self._initialized or self._client is None:
            raise RuntimeError("GoogleAdapter.initialize() must be called first.")
        return self._client

    # ----------------------------------------------------------- I/O surface

    async def complete(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> CompletionResult:
        self._validate_model(model)
        client = self._require_client()
        contents, system_instruction = self._convert_messages(messages)
        config = self._build_generation_config(system_instruction, kwargs)

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            raise self._translate_error(model, e) from e

        usage = self._extract_usage(response)
        cost = self._compute_cost(
            model,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

        return CompletionResult(
            content=self._extract_text(response),
            model=model,
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
        self._validate_model(model)
        client = self._require_client()
        contents, system_instruction = self._convert_messages(messages)
        config = self._build_generation_config(system_instruction, kwargs)

        try:
            stream_obj = await client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            raise self._translate_error(model, e) from e

        async for chunk in stream_obj:
            text = self._extract_text(chunk)
            if text:
                yield text

    async def list_models(self) -> List[ModelInfo]:
        client = self._require_client()
        out: List[ModelInfo] = []
        try:
            pager = await client.aio.models.list()
        except Exception as e:
            logger.error("GoogleAdapter.list_models failed: %s", e)
            return out

        async for m in pager:
            full_name = getattr(m, "name", "") or ""
            short = full_name.split("/")[-1] if "/" in full_name else full_name
            if not short:
                continue
            # Only include models this adapter is allowed to serve.
            if not any(short.startswith(p) for p in self.SUPPORTED_MODEL_PREFIXES):
                continue

            pricing = self._pricing.get(short, {})
            input_per_1k = (
                pricing["input_per_1m"] / 1000.0 if "input_per_1m" in pricing else None
            )
            output_per_1k = (
                pricing["output_per_1m"] / 1000.0 if "output_per_1m" in pricing else None
            )

            description = (getattr(m, "description", "") or "").lower()
            actions = [
                str(s).lower() for s in (getattr(m, "supported_actions", []) or [])
            ]
            supports_vision = "image" in description or "vision" in description or any(
                "image" in a for a in actions
            )

            out.append(
                ModelInfo(
                    id=short,
                    name=getattr(m, "display_name", short) or short,
                    provider=self.provider_name,
                    context_window=getattr(m, "input_token_limit", None),
                    max_output_tokens=getattr(m, "output_token_limit", None),
                    supports_streaming=True,
                    supports_vision=supports_vision,
                    input_cost_per_1k=input_per_1k,
                    output_cost_per_1k=output_per_1k,
                    metadata={
                        "full_name": full_name,
                        "description": getattr(m, "description", None),
                    },
                )
            )
        return out

    async def health_check(self) -> HealthStatus:
        if not self._initialized or self._client is None:
            return HealthStatus.UNKNOWN
        try:
            pager = await self._client.aio.models.list()
            # Touch the iterator to force at least one network round-trip.
            async for _ in pager:
                break
            return HealthStatus.HEALTHY
        except Exception as e:
            msg = str(e).lower()
            if any(tok in msg for tok in ("auth", "api key", "permission", "401", "403")):
                logger.warning("GoogleAdapter health check: auth failure: %s", e)
                return HealthStatus.UNREACHABLE
            if any(tok in msg for tok in ("timeout", "connection", "network", "unavailable")):
                logger.warning("GoogleAdapter health check: transport failure: %s", e)
                return HealthStatus.UNREACHABLE
            logger.warning("GoogleAdapter health check degraded: %s", e)
            return HealthStatus.DEGRADED

    async def estimate_cost(
        self,
        model: str,
        messages: List[Dict[str, Any]],
    ) -> float:
        client = self._require_client()
        contents, _ = self._convert_messages(messages)
        prompt_tokens = 0
        try:
            count_result = await client.aio.models.count_tokens(
                model=model,
                contents=contents,
            )
            prompt_tokens = int(getattr(count_result, "total_tokens", 0) or 0)
        except Exception as e:
            logger.debug("count_tokens unavailable (%s); falling back to char/4 heuristic", e)
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            prompt_tokens = max(1, total_chars // 4)

        # We cannot know completion_tokens in advance; report prompt-only cost
        # as the conservative lower bound for budgeting.
        return self._compute_cost(model, prompt_tokens, 0)

    # ------------------------------------------------------------- internals

    def _validate_model(self, model: str) -> None:
        if not any(model.startswith(p) for p in self.SUPPORTED_MODEL_PREFIXES):
            raise ValueError(
                f"GoogleAdapter does not serve model '{model}'. "
                f"Supported prefixes: {self.SUPPORTED_MODEL_PREFIXES}."
            )

    def _compute_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = self._pricing.get(model)
        if not pricing:
            return 0.0
        input_cost = pricing.get("input_per_1m", 0.0) * prompt_tokens / 1_000_000.0
        output_cost = pricing.get("output_per_1m", 0.0) * completion_tokens / 1_000_000.0
        return round(input_cost + output_cost, 6)

    @staticmethod
    def _translate_error(model: str, exc: Exception) -> Exception:
        msg = str(exc).lower()
        if any(tok in msg for tok in ("not found", "404", "invalid model", "unknown model")):
            return ValueError(f"Model not available on Google Gemini: {model}")
        if any(tok in msg for tok in ("401", "403", "api key", "permission")):
            return PermissionError(f"Google Gemini authentication failed: {exc}")
        return exc

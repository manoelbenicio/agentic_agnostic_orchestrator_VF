"""OpenAI-compatible LLM gateway client."""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx


@dataclass(frozen=True, slots=True)
class LLMGatewayConfig:
    upstream_base_url: str | None = None
    api_key: str | None = None
    api_keys: tuple[str, ...] = ()
    default_model: str | None = None
    timeout_s: float = 60.0
    cache_ttl_s: float = 0.0
    quota_per_minute: int = 0

    @property
    def configured(self) -> bool:
        return bool(self.upstream_base_url)

    @property
    def upstream_keys(self) -> tuple[str, ...]:
        keys = self.api_keys
        if self.api_key and self.api_key not in keys:
            keys = (self.api_key, *keys)
        return keys


class LLMGatewayUnavailable(RuntimeError):
    """Raised when the gateway is not configured."""


class LLMGatewayUpstreamError(RuntimeError):
    """Raised when the upstream provider returns an error response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(f"upstream LLM provider returned HTTP {status_code}")
        self.status_code = status_code
        self.detail = detail


class LLMGatewayQuotaExceeded(RuntimeError):
    """Raised when a gateway consumer exceeds its configured request quota."""


class LLMGatewayService:
    """Small proxy service for OpenAI-compatible chat/models endpoints."""

    def __init__(
        self,
        config: LLMGatewayConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._quota_windows: dict[str, deque[float]] = defaultdict(deque)
        self._key_index = 0

    async def chat_completions(self, payload: dict[str, Any], *, consumer_id: str = "default") -> dict[str, Any]:
        if payload.get("stream") is True:
            raise ValueError("streaming responses are not supported by the control-plane proxy yet")
        self._check_quota(consumer_id)

        body = dict(payload)
        if not body.get("model") and self.config.default_model:
            body["model"] = self.config.default_model

        cache_key = self._cache_key("chat/completions", body)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        response = await self._request("POST", "chat/completions", json=body)
        data = self._json_response(response)
        self._set_cached(cache_key, data)
        return data

    async def list_models(self) -> dict[str, Any]:
        cache_key = self._cache_key("models", {})
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached
        response = await self._request("GET", "models")
        data = self._json_response(response)
        self._set_cached(cache_key, data)
        return data

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.config.upstream_base_url:
            raise LLMGatewayUnavailable("LLM gateway upstream is not configured")

        headers = kwargs.pop("headers", {})
        api_key = self._next_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        timeout = httpx.Timeout(self.config.timeout_s)
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            try:
                response = await client.request(
                    method,
                    urljoin(self.config.upstream_base_url.rstrip("/") + "/", path),
                    headers=headers,
                    **kwargs,
                )
            except httpx.TimeoutException as exc:
                raise LLMGatewayUnavailable("LLM gateway upstream timed out") from exc
            except httpx.HTTPError as exc:
                raise LLMGatewayUnavailable(f"LLM gateway upstream request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMGatewayUpstreamError(response.status_code, _response_detail(response))
        return response

    def _next_api_key(self) -> str | None:
        keys = self.config.upstream_keys
        if not keys:
            return None
        key = keys[self._key_index % len(keys)]
        self._key_index += 1
        return key

    def _check_quota(self, consumer_id: str) -> None:
        if self.config.quota_per_minute <= 0:
            return
        now = time.monotonic()
        window = self._quota_windows[consumer_id]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self.config.quota_per_minute:
            raise LLMGatewayQuotaExceeded("LLM gateway quota exceeded")
        window.append(now)

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        if self.config.cache_ttl_s <= 0:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, data = entry
        if time.monotonic() >= expires_at:
            self._cache.pop(key, None)
            return None
        return json.loads(json.dumps(data))

    def _set_cached(self, key: str, data: dict[str, Any]) -> None:
        if self.config.cache_ttl_s <= 0:
            return
        self._cache[key] = (time.monotonic() + self.config.cache_ttl_s, json.loads(json.dumps(data)))

    @staticmethod
    def _cache_key(path: str, payload: dict[str, Any]) -> str:
        raw = json.dumps({"path": path, "payload": payload}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _json_response(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMGatewayUnavailable("LLM gateway upstream returned non-JSON response") from exc
        if not isinstance(data, dict):
            raise LLMGatewayUnavailable("LLM gateway upstream returned an invalid JSON payload")
        return data


def _response_detail(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"message": response.text}

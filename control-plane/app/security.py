"""HTTP security middleware for the integrated control plane."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import RLock
from urllib.parse import unquote_plus

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


_WAF_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"<\s*script\b",
        r"javascript\s*:",
        r"\bunion\s+select\b",
        r"\b(or|and)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+",
        r"\b(drop|alter|truncate)\s+table\b",
        r"\b(sleep|benchmark)\s*\(",
        r"\.\./|\.\.\\",
        r"\$\{[^}]+}",
        r"\{\{[^}]+}}",
    )
)


@dataclass(frozen=True, slots=True)
class SecurityMiddlewareConfig:
    """Runtime knobs for local rate limiting and request filtering."""

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 300
    rate_limit_window_s: float = 60.0
    rate_limit_exempt_paths: tuple[str, ...] = ("/health", "/health/ready", "/metrics")
    waf_enabled: bool = True
    waf_max_body_bytes: int = 1_048_576


class SecurityMiddleware:
    """Reject abusive requests before route handlers and repositories run."""

    def __init__(self, app: ASGIApp, config: SecurityMiddlewareConfig) -> None:
        self.app = app
        self._config = config
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        waf_response, receive = await self._waf_response(scope, receive)
        if waf_response is not None:
            await waf_response(scope, receive, send)
            return

        rate_limited = self._rate_limit_response(scope)
        if rate_limited is not None:
            await rate_limited(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                self._attach_rate_limit_headers(scope, message)
            await send(message)

        await self.app(scope, receive, send_with_security_headers)

    async def _waf_response(self, scope: Scope, receive: Receive) -> tuple[Response | None, Receive]:
        if not self._config.waf_enabled:
            return None, receive

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._config.waf_max_body_bytes:
                    return (
                        _security_error(413, "request_body_too_large", "request body exceeds configured WAF limit"),
                        receive,
                    )
            except ValueError:
                return _security_error(400, "invalid_content_length", "invalid Content-Length header"), receive

        samples = [
            str(scope.get("path", "")),
            unquote_plus(scope.get("query_string", b"").decode("latin-1", errors="ignore")),
            headers.get("user-agent", ""),
            headers.get("referer", ""),
        ]

        body = b""
        if scope.get("method") in {"POST", "PUT", "PATCH"}:
            body = await _read_body(receive)
            if len(body) > self._config.waf_max_body_bytes:
                return (
                    _security_error(413, "request_body_too_large", "request body exceeds configured WAF limit"),
                    _replay_body(body),
                )
            content_type = headers.get("content-type", "")
            if _inspectable_content_type(content_type):
                samples.append(body.decode("utf-8", errors="ignore"))
            receive = _replay_body(body)

        for sample in samples:
            if sample and _matches_waf(sample):
                return _security_error(403, "waf_blocked", "request rejected by WAF rules"), receive
        return None, receive

    def _rate_limit_response(self, scope: Scope) -> Response | None:
        if not self._config.rate_limit_enabled or scope.get("method") == "OPTIONS":
            return None
        if _path_is_exempt(str(scope.get("path", "")), self._config.rate_limit_exempt_paths):
            return None
        if self._config.rate_limit_requests <= 0:
            return None

        now = time.monotonic()
        window_start = now - self._config.rate_limit_window_s
        client_key = _client_key(scope)
        with self._lock:
            hits = self._hits[client_key]
            while hits and hits[0] <= window_start:
                hits.popleft()
            if len(hits) >= self._config.rate_limit_requests:
                retry_after = max(1, int(hits[0] + self._config.rate_limit_window_s - now))
                return _rate_limit_error(self._config.rate_limit_requests, retry_after)
            hits.append(now)
        return None

    def _attach_rate_limit_headers(self, scope: Scope, message: Message) -> None:
        if not self._config.rate_limit_enabled or _path_is_exempt(
            str(scope.get("path", "")),
            self._config.rate_limit_exempt_paths,
        ):
            return
        if self._config.rate_limit_requests <= 0:
            return
        now = time.monotonic()
        client_key = _client_key(scope)
        with self._lock:
            hits = self._hits.get(client_key, deque())
            remaining = max(0, self._config.rate_limit_requests - len(hits))
            reset = 0 if not hits else max(0, int(hits[0] + self._config.rate_limit_window_s - now))
        headers = MutableHeaders(scope=message)
        headers["X-RateLimit-Limit"] = str(self._config.rate_limit_requests)
        headers["X-RateLimit-Remaining"] = str(remaining)
        headers["X-RateLimit-Reset"] = str(reset)


def _security_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": {"code": code, "message": message}})


def _rate_limit_error(limit: int, retry_after: int) -> JSONResponse:
    response = _security_error(429, "rate_limited", "too many requests")
    response.headers["Retry-After"] = str(retry_after)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = "0"
    response.headers["X-RateLimit-Reset"] = str(retry_after)
    return response


def _matches_waf(sample: str) -> bool:
    return any(pattern.search(sample) for pattern in _WAF_PATTERNS)


def _inspectable_content_type(content_type: str) -> bool:
    if not content_type:
        return True
    return any(token in content_type for token in ("json", "text", "xml", "form"))


def _path_is_exempt(path: str, exempt_paths: Iterable[str]) -> bool:
    return any(path == exempt or path.startswith(f"{exempt}/") for exempt in exempt_paths)


def _client_key(scope: Scope) -> str:
    headers = Headers(scope=scope)
    client = scope.get("client")
    client_host = client[0] if client else "unknown"
    return f"{client_host}:{headers.get('x-aop-consumer', 'default')}"


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay_body(body: bytes) -> Callable[[], Message]:
    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    return receive

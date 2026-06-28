from __future__ import annotations

import asyncio
import json
from typing import Any

from app.main import create_app
from app.security import SecurityMiddleware, SecurityMiddlewareConfig
from app.settings import Settings


async def _ok_app(scope, receive, send) -> None:
    assert scope["type"] == "http"
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b'{"status":"ok"}'})


def _call(
    app: SecurityMiddleware,
    *,
    method: str = "GET",
    path: str = "/ok",
    query: bytes = b"",
    body: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
    }
    asyncio.run(app(scope, receive, send))

    start = next(message for message in messages if message["type"] == "http.response.start")
    raw_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    response_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return start["status"], response_headers, json.loads(raw_body or b"{}")


def test_rate_limit_blocks_client_after_configured_budget():
    config = SecurityMiddlewareConfig(
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_s=60,
        rate_limit_exempt_paths=(),
        waf_enabled=False,
    )
    app = SecurityMiddleware(_ok_app, config=config)

    assert _call(app)[0] == 200
    second_status, second_headers, _ = _call(app)
    blocked_status, blocked_headers, blocked_body = _call(app)

    assert second_status == 200
    assert second_headers["x-ratelimit-remaining"] == "0"
    assert blocked_status == 429
    assert blocked_body["detail"]["code"] == "rate_limited"
    assert blocked_headers["retry-after"]
    assert blocked_headers["x-ratelimit-remaining"] == "0"


def test_rate_limit_exempts_health_paths():
    config = SecurityMiddlewareConfig(
        rate_limit_enabled=True,
        rate_limit_requests=1,
        rate_limit_window_s=60,
        rate_limit_exempt_paths=("/health",),
        waf_enabled=False,
    )
    app = SecurityMiddleware(_ok_app, config=config)

    assert _call(app, path="/healthz")[0] == 200
    assert _call(app, path="/healthz")[0] == 429
    assert _call(app, path="/health/extra")[0] == 200


def test_waf_blocks_suspicious_query_before_routing():
    status, _, body = _call(
        SecurityMiddleware(_ok_app, config=SecurityMiddlewareConfig(rate_limit_enabled=False, waf_enabled=True)),
        query=b"filter=%27%20OR%201%3D1",
    )

    assert status == 403
    assert body["detail"]["code"] == "waf_blocked"


def test_waf_blocks_suspicious_json_body_before_routing():
    status, _, body = _call(
        SecurityMiddleware(_ok_app, config=SecurityMiddlewareConfig(rate_limit_enabled=False, waf_enabled=True)),
        method="POST",
        path="/echo",
        body=b'{"message":"<script>alert(1)</script>"}',
        headers=[(b"content-type", b"application/json")],
    )

    assert status == 403
    assert body["detail"]["code"] == "waf_blocked"


def test_waf_rejects_oversized_body():
    status, _, body = _call(
        SecurityMiddleware(
            _ok_app,
            config=SecurityMiddlewareConfig(rate_limit_enabled=False, waf_enabled=True, waf_max_body_bytes=8),
        ),
        method="POST",
        path="/echo",
        body=b"0123456789",
        headers=[(b"content-type", b"text/plain")],
    )

    assert status == 413
    assert body["detail"]["code"] == "request_body_too_large"


def test_create_app_installs_security_middleware():
    app = create_app(Settings(security_rate_limit_requests=17, security_waf_max_body_bytes=128))

    middleware = next(item for item in app.user_middleware if item.cls is SecurityMiddleware)

    assert middleware.kwargs["config"].rate_limit_requests == 17
    assert middleware.kwargs["config"].waf_max_body_bytes == 128

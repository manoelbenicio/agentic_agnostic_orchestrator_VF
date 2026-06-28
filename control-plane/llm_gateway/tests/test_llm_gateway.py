from __future__ import annotations

import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway import LLMGatewayConfig, LLMGatewayService, build_llm_gateway_router


def _client(service: LLMGatewayService, config: LLMGatewayConfig) -> TestClient:
    app = FastAPI()
    app.include_router(build_llm_gateway_router(config, prefix="/llm", service=service))
    app.include_router(build_llm_gateway_router(config, prefix="/api/v1/llm-proxy", service=service))
    return TestClient(app)


def test_chat_completions_proxies_openai_payload_and_adds_default_model() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "chatcmpl-test", "choices": [{"message": {"content": "ok"}}]})

    config = LLMGatewayConfig(
        upstream_base_url="http://provider.test/v1",
        api_key="secret",
        default_model="glm-5.2",
        timeout_s=10.0,
    )
    service = LLMGatewayService(config, transport=httpx.MockTransport(handler))
    client = _client(service, config)

    response = client.post(
        "/llm/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "ok"
    assert captured["url"] == "http://provider.test/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    assert captured["body"] == {"messages": [{"role": "user", "content": "hello"}], "model": "glm-5.2"}


def test_gateway_reports_unconfigured_upstream() -> None:
    config = LLMGatewayConfig()
    client = _client(LLMGatewayService(config), config)

    health = client.get("/llm/health")
    assert health.status_code == 200
    assert health.json()["configured"] is False
    assert health.json()["api_key_configured"] is False

    response = client.post("/llm/chat/completions", json={"model": "glm-5.2", "messages": []})
    assert response.status_code == 503


def test_gateway_rejects_streaming_until_supported() -> None:
    config = LLMGatewayConfig(upstream_base_url="http://provider.test/v1")
    client = _client(LLMGatewayService(config), config)

    response = client.post(
        "/llm/chat/completions",
        json={"model": "glm-5.2", "messages": [], "stream": True},
    )

    assert response.status_code == 400
    assert "streaming" in response.json()["detail"]


def test_llm_proxy_alias_supports_cache_and_key_rotation() -> None:
    calls: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("authorization"))
        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-{len(calls)}",
                "choices": [{"message": {"content": "cached"}}],
            },
        )

    config = LLMGatewayConfig(
        upstream_base_url="http://provider.test/v1",
        api_keys=("key-a", "key-b"),
        cache_ttl_s=60.0,
    )
    service = LLMGatewayService(config, transport=httpx.MockTransport(handler))
    client = _client(service, config)

    first = client.post(
        "/api/v1/llm-proxy/chat/completions",
        json={"model": "glm-5.2", "messages": [{"role": "user", "content": "hello"}]},
    )
    second = client.post(
        "/api/v1/llm-proxy/chat/completions",
        json={"model": "glm-5.2", "messages": [{"role": "user", "content": "hello"}]},
    )
    third = client.post(
        "/api/v1/llm-proxy/chat/completions",
        json={"model": "glm-5.2", "messages": [{"role": "user", "content": "different"}]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert third.json()["id"] == "chatcmpl-2"
    assert calls == ["Bearer key-a", "Bearer key-b"]


def test_llm_proxy_enforces_consumer_quota() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "ok", "choices": []})

    config = LLMGatewayConfig(
        upstream_base_url="http://provider.test/v1",
        quota_per_minute=1,
    )
    service = LLMGatewayService(config, transport=httpx.MockTransport(handler))
    client = _client(service, config)

    first = client.post(
        "/api/v1/llm-proxy/chat/completions",
        headers={"X-AOP-Consumer": "agent-1"},
        json={"model": "glm-5.2", "messages": []},
    )
    second = client.post(
        "/api/v1/llm-proxy/chat/completions",
        headers={"X-AOP-Consumer": "agent-1"},
        json={"model": "glm-5.2", "messages": [{"role": "user", "content": "again"}]},
    )

    assert first.status_code == 200
    assert second.status_code == 429

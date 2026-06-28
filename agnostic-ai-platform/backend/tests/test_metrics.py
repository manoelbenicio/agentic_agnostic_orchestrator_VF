from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.metrics import (
    litellm_failure_callback,
    litellm_success_callback,
    record_llm_fallback,
    record_llm_token_usage,
    set_active_agents,
    set_websocket_connections,
)


def test_metrics_endpoint_exposes_http_latency_errors_and_token_usage() -> None:
    client = TestClient(create_app())

    client.get("/health")
    client.get("/missing")
    record_llm_token_usage(
        model="gpt-4o-mini",
        workspace="workspace-1",
        user="user-1",
        prompt_tokens=11,
        completion_tokens=13,
    )
    record_llm_fallback(from_model="gpt-4o-mini", to_model="claude-3-5-sonnet")
    set_active_agents(workspace="workspace-1", count=2)
    set_websocket_connections(workspace="workspace-1", count=1)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert 'agnosticai_http_requests_total{method="GET",path="/health",status="200"}' in body
    assert 'agnosticai_http_errors_total{method="GET",path="/missing",status="401"}' in body
    assert 'agnosticai_http_request_duration_seconds_bucket{le="0.005",method="GET",path="/health"}' in body
    assert (
        'agnosticai_llm_tokens_total{model="gpt-4o-mini",provider="openai",token_type="total",user="user-1",workspace="workspace-1"} 24.0'
        in body
    )
    assert (
        'agnosticai_llm_token_usage{model="gpt-4o-mini",provider="openai",token_type="total",user="user-1",workspace="workspace-1"} 24.0'
        in body
    )
    assert (
        'agnosticai_llm_token_usage_total{model="gpt-4o-mini",provider="openai",user="user-1",workspace="workspace-1"} 24.0'
        in body
    )
    assert 'agnosticai_llm_input_tokens_total{model="gpt-4o-mini",provider="openai",user="user-1",workspace="workspace-1"} 11.0' in body
    assert 'agnosticai_llm_output_tokens_total{model="gpt-4o-mini",provider="openai",user="user-1",workspace="workspace-1"} 13.0' in body
    assert (
        'agnosticai_llm_fallback_total{from_model="gpt-4o-mini",to_model="claude-3-5-sonnet"} 1.0'
        in body
    )
    assert 'agnosticai_active_agents{workspace="workspace-1"} 2.0' in body
    assert 'agnosticai_websocket_connections{workspace="workspace-1"} 1.0' in body
    assert 'agnosticai_http_active_connections{method="GET",path="/health"} 0.0' in body


def test_litellm_success_callback_records_input_output_tokens_and_cost() -> None:
    client = TestClient(create_app())

    litellm_success_callback(
        {
            "model": "gpt-4o-mini",
            "metadata": {"workspace": "workspace-cb", "user": "user-cb"},
            "response_cost": 0.0042,
        },
        {
            "model": "gpt-4o-mini",
            "usage": {
                "prompt_tokens": 17,
                "completion_tokens": 19,
                "total_tokens": 36,
            },
        },
    )

    body = client.get("/metrics").text

    assert 'agnosticai_llm_input_tokens_total{model="gpt-4o-mini",provider="openai",user="user-cb",workspace="workspace-cb"} 17.0' in body
    assert 'agnosticai_llm_output_tokens_total{model="gpt-4o-mini",provider="openai",user="user-cb",workspace="workspace-cb"} 19.0' in body
    assert 'agnosticai_llm_cost_usd_total{model="gpt-4o-mini",provider="openai",user="user-cb",workspace="workspace-cb"} 0.0042' in body
    assert 'agnosticai_llm_token_usage_total{model="gpt-4o-mini",provider="openai",user="user-cb",workspace="workspace-cb"} 36.0' in body


def test_litellm_success_callback_calculates_cost_when_missing() -> None:
    client = TestClient(create_app())

    litellm_success_callback(
        {
            "model": "gpt-4o-mini",
            "metadata": {"workspace": "workspace-cost", "user": "user-cost"},
        },
        {
            "model": "gpt-4o-mini",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 1000,
                "total_tokens": 2000,
            },
        },
    )

    body = client.get("/metrics").text

    assert 'agnosticai_llm_cost_usd_total{model="gpt-4o-mini",provider="openai",user="user-cost",workspace="workspace-cost"} 0.00075' in body


def test_litellm_failure_callback_records_provider_model_and_error() -> None:
    client = TestClient(create_app())

    litellm_failure_callback(
        {
            "model": "claude-3-5-sonnet",
            "metadata": {"workspace": "workspace-fail", "user": "user-fail"},
        },
        exception=TimeoutError("provider timeout"),
    )

    body = client.get("/metrics").text

    assert 'agnosticai_llm_requests_total{model="claude-3-5-sonnet",provider="anthropic",status="failure",user="user-fail",workspace="workspace-fail"} 1.0' in body
    assert 'agnosticai_llm_failure_total{error_type="TimeoutError",model="claude-3-5-sonnet",provider="anthropic",user="user-fail",workspace="workspace-fail"} 1.0' in body

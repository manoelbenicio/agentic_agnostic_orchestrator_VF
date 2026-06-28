from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import app.tracing as tracing


class FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}
        self.exceptions: list[BaseException] = []
        self.status: Any = None

    def __enter__(self) -> "FakeSpan":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, exception: BaseException) -> None:
        self.exceptions.append(exception)

    def set_status(self, status: Any) -> None:
        self.status = status


class FakeTracer:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []

    def start_as_current_span(self, name: str, kind: Any = None) -> FakeSpan:
        span = FakeSpan()
        span.set_attribute("span.name", name)
        span.set_attribute("span.kind", kind)
        self.spans.append(span)
        return span


def test_record_llm_request_span_sets_model_provider_usage_cost_and_latency(monkeypatch) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(tracing, "get_tracer", lambda: tracer)

    tracing.record_llm_request_span(
        model="gpt-4o-mini",
        workspace="workspace-1",
        user="user-1",
        prompt_tokens=11,
        completion_tokens=13,
        total_tokens=24,
        cost_usd="0.0042",
        latency_ms=123.4567,
        metadata={"request_id": "req-1"},
    )

    attrs = tracer.spans[0].attributes
    assert attrs["span.name"] == "llm.request"
    assert attrs["llm.model"] == "gpt-4o-mini"
    assert attrs["llm.provider"] == "openai"
    assert attrs["llm.workspace"] == "workspace-1"
    assert attrs["llm.user"] == "user-1"
    assert attrs["llm.prompt_tokens"] == 11
    assert attrs["llm.completion_tokens"] == 13
    assert attrs["llm.total_tokens"] == 24
    assert attrs["llm.cost_usd"] == 0.0042
    assert attrs["llm.latency_ms"] == 123.457
    assert attrs["llm.request_id"] == "req-1"
    assert attrs["gen_ai.system"] == "openai"
    assert attrs["gen_ai.request.model"] == "gpt-4o-mini"
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 13


def test_litellm_success_tracing_callback_extracts_usage_metadata_cost_and_latency(monkeypatch) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(tracing, "get_tracer", lambda: tracer)
    start = datetime.now(timezone.utc)
    end = start + timedelta(milliseconds=250)

    tracing.litellm_success_tracing_callback(
        {
            "model": "claude-3-5-sonnet",
            "metadata": {"workspace": "workspace-cb", "user": "user-cb", "provider": "anthropic"},
            "response_cost": 0.0084,
        },
        {
            "model": "claude-3-5-sonnet",
            "usage": {"prompt_tokens": 17, "completion_tokens": 19, "total_tokens": 36},
        },
        start_time=start,
        end_time=end,
    )

    attrs = tracer.spans[0].attributes
    assert attrs["llm.model"] == "claude-3-5-sonnet"
    assert attrs["llm.provider"] == "anthropic"
    assert attrs["llm.workspace"] == "workspace-cb"
    assert attrs["llm.user"] == "user-cb"
    assert attrs["llm.prompt_tokens"] == 17
    assert attrs["llm.completion_tokens"] == 19
    assert attrs["llm.total_tokens"] == 36
    assert attrs["llm.cost_usd"] == 0.0084
    assert attrs["llm.latency_ms"] == 250.0


def test_litellm_failure_tracing_callback_marks_span_error(monkeypatch) -> None:
    tracer = FakeTracer()
    monkeypatch.setattr(tracing, "get_tracer", lambda: tracer)
    error = TimeoutError("provider timeout")

    tracing.litellm_failure_tracing_callback(
        {"model": "gemini-1.5-flash", "metadata": {"workspace": "workspace-fail", "user": "user-fail"}},
        exception=error,
    )

    span = tracer.spans[0]
    assert span.attributes["llm.model"] == "gemini-1.5-flash"
    assert span.attributes["llm.provider"] == "google"
    assert span.attributes["llm.error"] is True
    assert span.attributes["llm.error_type"] == "TimeoutError"
    assert span.exceptions == [error]


def test_inject_trace_context_returns_mutable_carrier() -> None:
    headers = tracing.inject_trace_context({"x-request-id": "req-1"})

    assert headers["x-request-id"] == "req-1"
    assert isinstance(headers, dict)

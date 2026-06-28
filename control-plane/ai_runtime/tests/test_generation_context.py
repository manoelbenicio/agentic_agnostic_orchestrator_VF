from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_runtime import (
    ChatMessage,
    DeterministicGenerationClient,
    GenerationRequest,
    GenerationResponse,
    MessageRole,
    fit_context_window,
    generate_completion,
)


def _message(role: MessageRole, content: str) -> ChatMessage:
    return ChatMessage(role=role, content=content)


def test_context_window_preserves_system_and_latest_user_while_dropping_oldest() -> None:
    messages = (
        _message(MessageRole.SYSTEM, "Follow AOP runbook rules."),
        _message(MessageRole.USER, "Old request " + "alpha " * 80),
        _message(MessageRole.ASSISTANT, "Old answer " + "beta " * 80),
        _message(MessageRole.USER, "Current request: summarize live deployment status."),
    )

    fitted = fit_context_window(messages, context_window_tokens=90, max_output_tokens=30)

    assert fitted.messages[0].role == MessageRole.SYSTEM
    assert fitted.messages[-1].content == "Current request: summarize live deployment status."
    assert fitted.prompt_tokens <= fitted.available_prompt_tokens
    assert fitted.dropped_count >= 1


def test_context_window_truncates_mandatory_message_when_prompt_budget_is_tiny() -> None:
    messages = (
        _message(MessageRole.SYSTEM, "Always respond with operational precision."),
        _message(MessageRole.USER, "Please analyze " + "a very long context " * 120),
    )

    fitted = fit_context_window(messages, context_window_tokens=48, max_output_tokens=20)

    assert fitted.truncated_count >= 1
    assert fitted.prompt_tokens <= fitted.available_prompt_tokens
    assert any("[truncated]" in message.content for message in fitted.messages)


def test_generation_request_rejects_output_budget_that_consumes_context_window() -> None:
    with pytest.raises(ValidationError, match="max_output_tokens must be smaller"):
        GenerationRequest(
            model="glm-5.2",
            messages=(_message(MessageRole.USER, "hello"),),
            context_window_tokens=100,
            max_output_tokens=100,
        )


def test_generation_response_requires_consistent_token_totals() -> None:
    with pytest.raises(ValidationError, match="total_tokens must equal"):
        GenerationResponse(
            model="glm-5.2",
            content="bad accounting",
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=99,
        )


def test_deterministic_generation_uses_fitted_latest_user_and_stop_sequence() -> None:
    messages = (
        _message(MessageRole.SYSTEM, "You are an AOP agent."),
        _message(MessageRole.USER, "Ignore older request."),
        _message(MessageRole.ASSISTANT, "Older answer."),
        _message(MessageRole.USER, "Return deployment summary. STOP secret tail"),
    )

    response = generate_completion(
        DeterministicGenerationClient(),
        model="glm-5.2",
        messages=messages,
        context_window_tokens=160,
        max_output_tokens=40,
        stop=("STOP",),
    )

    assert response.model == "glm-5.2"
    assert response.content == "[glm-5.2] Return deployment summary. "
    assert response.metadata["deterministic"] is True
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens

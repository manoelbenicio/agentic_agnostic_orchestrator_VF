"""Generation helpers with deterministic test doubles."""

from __future__ import annotations

from typing import Protocol

from .context_window import estimate_tokens, fit_context_window
from .models import ChatMessage, GenerationRequest, GenerationResponse, MessageRole


class GenerationClient(Protocol):
    """Minimal protocol implemented by concrete LLM gateway clients."""

    def complete(self, request: GenerationRequest) -> GenerationResponse:
        """Return a normalized completion response."""


class DeterministicGenerationClient:
    """Local test double that never calls a remote LLM provider."""

    def complete(self, request: GenerationRequest) -> GenerationResponse:
        last_user = next(
            (message for message in reversed(request.messages) if message.role == MessageRole.USER),
            request.messages[-1],
        )
        content = f"[{request.model}] {last_user.content.strip()}"
        for stop in request.stop:
            index = content.find(stop)
            if index >= 0:
                content = content[:index]
                break
        completion_tokens = min(estimate_tokens(content), request.max_output_tokens)
        prompt_tokens = sum(4 + estimate_tokens(message.content) for message in request.messages)
        return GenerationResponse(
            model=request.model,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason="stop",
            metadata={"deterministic": True},
        )


def generate_completion(
    client: GenerationClient,
    *,
    model: str,
    messages: tuple[ChatMessage, ...] | list[ChatMessage],
    context_window_tokens: int,
    max_output_tokens: int,
    temperature: float = 0.2,
    stop: tuple[str, ...] = (),
) -> GenerationResponse:
    """Fit context and execute a normalized generation request."""
    fitted = fit_context_window(
        tuple(messages),
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
    )
    request = GenerationRequest(
        model=model,
        messages=fitted.messages,
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        stop=stop,
        metadata={
            "dropped_context_messages": fitted.dropped_count,
            "truncated_context_messages": fitted.truncated_count,
        },
    )
    return client.complete(request)

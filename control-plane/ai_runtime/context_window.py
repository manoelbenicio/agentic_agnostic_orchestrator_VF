"""Deterministic context-window fitting for chat generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .models import ChatMessage, MessageRole


class ContextWindowResult(BaseModel):
    """Messages selected for a model context window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: tuple[ChatMessage, ...]
    prompt_tokens: int = Field(ge=0)
    dropped_count: int = Field(ge=0)
    truncated_count: int = Field(ge=0)
    available_prompt_tokens: int = Field(ge=0)


def estimate_tokens(text: str) -> int:
    """Return a stable conservative token estimate without tokenizer deps."""
    stripped = text.strip()
    if not stripped:
        return 0
    # Approximate common BPE behavior: one token per 4 chars plus word boundary
    # pressure. This intentionally overestimates short operational prompts.
    return max(1, (len(stripped) + 3) // 4, len(stripped.split()))


def _message_tokens(message: ChatMessage) -> int:
    return 4 + estimate_tokens(message.content)


def _total_tokens(messages: tuple[ChatMessage, ...]) -> int:
    return sum(_message_tokens(message) for message in messages)


def _truncate_message(message: ChatMessage, max_tokens: int) -> ChatMessage:
    if max_tokens <= 4:
        return message.model_copy(update={"content": "[truncated]"})
    content_budget = max_tokens - 4
    words = message.content.split()
    kept: list[str] = []
    for word in words:
        candidate = " ".join([*kept, word])
        suffix_budget = estimate_tokens(" [truncated]")
        if estimate_tokens(candidate) + suffix_budget > content_budget:
            break
        kept.append(word)
    content = " ".join(kept).strip() or message.content[: max(16, content_budget * 4)].strip()
    if content != message.content:
        content = f"{content} [truncated]"
    while 4 + estimate_tokens(content) > max_tokens and " " in content:
        content = f"{content.rsplit(' ', 2)[0]} [truncated]"
    if 4 + estimate_tokens(content) > max_tokens:
        content = "[truncated]"
    return message.model_copy(update={"content": content})


def fit_context_window(
    messages: tuple[ChatMessage, ...] | list[ChatMessage],
    *,
    context_window_tokens: int,
    max_output_tokens: int,
) -> ContextWindowResult:
    """Fit messages into the prompt budget while preserving core intent.

    Policy:
    - reserve ``max_output_tokens`` for model output;
    - keep the first system message when present;
    - keep the newest user message;
    - fill remaining room with the newest prior messages;
    - truncate only messages that are mandatory to preserve.
    """
    if context_window_tokens <= 0:
        raise ValueError("context_window_tokens must be positive")
    if max_output_tokens <= 0:
        raise ValueError("max_output_tokens must be positive")
    if max_output_tokens >= context_window_tokens:
        raise ValueError("max_output_tokens must be smaller than context_window_tokens")

    source = tuple(messages)
    if not source:
        raise ValueError("messages must not be empty")

    available = context_window_tokens - max_output_tokens
    system = next((message for message in source if message.role == MessageRole.SYSTEM), None)
    last_user = next((message for message in reversed(source) if message.role == MessageRole.USER), None)
    mandatory = tuple(message for message in (system, last_user) if message is not None)
    if not mandatory:
        mandatory = (source[-1],)

    selected: list[ChatMessage] = []
    truncated = 0
    remaining = available
    for message in mandatory:
        tokens = _message_tokens(message)
        if tokens > remaining:
            message = _truncate_message(message, remaining)
            tokens = _message_tokens(message)
            truncated += 1
        if tokens <= remaining:
            selected.append(message)
            remaining -= tokens

    selected_ids = {id(message) for message in mandatory}
    candidates = [
        message
        for message in reversed(source)
        if id(message) not in selected_ids and message.role != MessageRole.SYSTEM
    ]
    for message in candidates:
        tokens = _message_tokens(message)
        if tokens <= remaining:
            selected.insert(1 if system is not None and selected else 0, message)
            remaining -= tokens

    ordered = tuple(selected)
    prompt_tokens = _total_tokens(ordered)
    return ContextWindowResult(
        messages=ordered,
        prompt_tokens=prompt_tokens,
        dropped_count=len(source) - len(ordered),
        truncated_count=truncated,
        available_prompt_tokens=available,
    )

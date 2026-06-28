"""Typed contracts shared by AI generation integrations."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MessageRole(StrEnum):
    """Supported chat roles for model-agnostic generation requests."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """A single chat message passed to an LLM runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: MessageRole
    content: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class GenerationRequest(BaseModel):
    """Model-agnostic generation request after context-window fitting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    messages: tuple[ChatMessage, ...] = Field(min_length=1)
    context_window_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    temperature: float = Field(default=0.2, ge=0, le=2)
    stop: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be blank")
        return value

    @field_validator("stop")
    @classmethod
    def stop_sequences_must_not_be_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError("stop sequences must not be blank")
        return value

    @model_validator(mode="after")
    def output_must_fit_context_window(self) -> "GenerationRequest":
        if self.max_output_tokens >= self.context_window_tokens:
            raise ValueError("max_output_tokens must be smaller than context_window_tokens")
        return self


class GenerationResponse(BaseModel):
    """Normalized response returned by a generation client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    content: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    finish_reason: str = Field(default="stop", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def total_tokens_must_match_usage(self) -> "GenerationResponse":
        expected = self.prompt_tokens + self.completion_tokens
        if self.total_tokens != expected:
            raise ValueError("total_tokens must equal prompt_tokens + completion_tokens")
        return self

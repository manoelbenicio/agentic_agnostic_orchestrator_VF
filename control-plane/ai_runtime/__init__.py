"""AI runtime contracts for generation and context-window handling."""

from .context_window import ContextWindowResult, estimate_tokens, fit_context_window
from .generation import DeterministicGenerationClient, generate_completion
from .glm_client import GlmGenerationClient
from .models import ChatMessage, GenerationRequest, GenerationResponse, MessageRole

__all__ = [
    "ChatMessage",
    "ContextWindowResult",
    "DeterministicGenerationClient",
    "GenerationRequest",
    "GenerationResponse",
    "GlmGenerationClient",
    "MessageRole",
    "estimate_tokens",
    "fit_context_window",
    "generate_completion",
]

"""Zhipu AI (GLM) generation client."""

from __future__ import annotations

import httpx

from .models import GenerationRequest, GenerationResponse


class GlmGenerationClient:
    """Client for Zhipu AI GLM models."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    ) -> None:
        """Initialize the client with an API key."""
        self.api_key = api_key
        self.base_url = base_url

    def complete(self, request: GenerationRequest) -> GenerationResponse:
        """Execute a generation request against the Zhipu AI API."""
        messages = [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.messages
        ]

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if request.stop:
            payload["stop"] = list(request.stop)

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            usage = data.get("usage", {})

            # Ensure total_tokens matches usage
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            return GenerationResponse(
                model=data.get("model", request.model),
                content=choice["message"]["content"],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                finish_reason=choice.get("finish_reason", "stop"),
                metadata=request.metadata,
            )

"""FastAPI routes for the LLM gateway proxy."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from .service import (
    LLMGatewayConfig,
    LLMGatewayQuotaExceeded,
    LLMGatewayService,
    LLMGatewayUnavailable,
    LLMGatewayUpstreamError,
)


class LLMGatewayHealthResponse(BaseModel):
    configured: bool
    upstream_base_url: str | None
    default_model: str | None
    api_key_configured: bool
    upstream_key_count: int
    timeout_s: float
    cache_ttl_s: float
    quota_per_minute: int


def build_llm_gateway_router(
    config: LLMGatewayConfig,
    *,
    prefix: str = "/llm",
    service: LLMGatewayService | None = None,
) -> APIRouter:
    """Build OpenAI-compatible LLM gateway routes."""

    router = APIRouter(prefix=prefix, tags=["llm-gateway"])
    gateway = service or LLMGatewayService(config)

    @router.get("/health", response_model=LLMGatewayHealthResponse)
    def health() -> LLMGatewayHealthResponse:
        return LLMGatewayHealthResponse(
            configured=config.configured,
            upstream_base_url=config.upstream_base_url,
            default_model=config.default_model,
            api_key_configured=bool(config.upstream_keys),
            upstream_key_count=len(config.upstream_keys),
            timeout_s=config.timeout_s,
            cache_ttl_s=config.cache_ttl_s,
            quota_per_minute=config.quota_per_minute,
        )

    @router.get("/models")
    async def list_models() -> dict[str, Any]:
        try:
            return await gateway.list_models()
        except LLMGatewayUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except LLMGatewayUpstreamError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"upstream_status": exc.status_code, "upstream": exc.detail},
            ) from exc

    @router.post("/chat/completions")
    async def chat_completions(
        payload: dict[str, Any] = Body(...),
        x_aop_consumer: str = Header(default="default"),
    ) -> dict[str, Any]:
        try:
            return await gateway.chat_completions(payload, consumer_id=x_aop_consumer)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except LLMGatewayQuotaExceeded as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
        except LLMGatewayUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except LLMGatewayUpstreamError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"upstream_status": exc.status_code, "upstream": exc.detail},
            ) from exc

    @router.post("/v1/chat/completions")
    async def chat_completions_v1(
        payload: dict[str, Any] = Body(...),
        x_aop_consumer: str = Header(default="default"),
    ) -> dict[str, Any]:
        return await chat_completions(payload, x_aop_consumer)

    @router.get("/v1/models")
    async def list_models_v1() -> dict[str, Any]:
        return await list_models()

    return router

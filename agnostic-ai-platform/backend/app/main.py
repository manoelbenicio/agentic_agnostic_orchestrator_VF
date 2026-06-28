from __future__ import annotations

from fastapi import FastAPI

from app.logging_config import CorrelationIdMiddleware, configure_logging
from app.metrics import PrometheusMiddleware, prometheus_response, register_litellm_success_callback
from app.tracing import register_litellm_tracing_callbacks, setup_opentelemetry


def create_app() -> FastAPI:
    configure_logging()
    register_litellm_success_callback()
    register_litellm_tracing_callbacks()
    app = FastAPI(title="AgnosticAI Platform API")

    from app.auth import JWTAuthMiddleware
    from app.tenant_isolation import TenantIsolationMiddleware
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(TenantIsolationMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    from app.routers import auth, llm
    from app.model_registry import router as model_registry_router
    from app.rag_ingestion import router as rag_ingestion_router
    from app.retrieval_chain import router as rag_router
    app.include_router(auth.router)
    app.include_router(llm.router)
    app.include_router(model_registry_router)
    app.include_router(rag_ingestion_router)
    app.include_router(rag_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return prometheus_response()

    setup_opentelemetry(app)

    return app


app = create_app()

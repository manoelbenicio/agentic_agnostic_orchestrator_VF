from __future__ import annotations

import logging
import os
import sys
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

CORRELATION_ID_HEADER = "x-correlation-id"
LOG_LEVEL_ENV = "AOP_LOG_LEVEL"


def configure_logging() -> None:
    log_level = _log_level_from_env()
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger().setLevel(log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            timestamper,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, header_name: str = CORRELATION_ID_HEADER) -> None:
        super().__init__(app)
        self.header_name = header_name
        self.logger = structlog.get_logger("agnosticai.request")

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        correlation_id = request.headers.get(self.header_name) or str(uuid4())
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        method = request.method
        path = _route_path(request)
        start = perf_counter()
        status_code = 500

        self.logger.info("request.started", method=method, path=path, client=_client_host(request))
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            self.logger.exception(
                "request.failed",
                method=method,
                path=path,
                status_code=status_code,
                latency_ms=_elapsed_ms(start),
            )
            raise
        finally:
            latency_ms = _elapsed_ms(start)
            self.logger.info(
                "request.finished",
                method=method,
                path=path,
                status_code=status_code,
                latency_ms=latency_ms,
            )
            if "response" in locals():
                response.headers[self.header_name] = correlation_id
            structlog.contextvars.clear_contextvars()


def get_logger(name: str | None = None):
    return structlog.get_logger(name)


def _log_level_from_env() -> int:
    configured = os.environ.get(LOG_LEVEL_ENV) or os.environ.get("LOG_LEVEL") or "INFO"
    return logging.getLevelName(configured.upper()) if isinstance(logging.getLevelName(configured.upper()), int) else logging.INFO


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


def _client_host(request: Request) -> str | None:
    return request.client.host if request.client else None


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)


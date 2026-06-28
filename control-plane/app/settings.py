"""Runtime settings for the FastAPI control plane."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_DATABASE_URL = "postgresql://aop_dev:aop_dev_postgres_20260626@127.0.0.1:5432/aop"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_CORS_ORIGINS = ("http://127.0.0.1:13000", "http://localhost:13000")


@dataclass(frozen=True, slots=True)
class Settings:
    """Environment-backed app settings."""

    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str = DEFAULT_REDIS_URL
    host: str = "127.0.0.1"
    port: int = 8090
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    seats_json: str | None = None
    seats_file: str | None = None
    device_login_commands_json: str | None = None
    herdmaster_url: str = "http://127.0.0.1:8080"
    herdmaster_token: str | None = None
    herdr_socket_path: str | None = None
    # Socket-mode polling: how often and how many times to poll HerdMaster for a
    # terminal task state when the task carries no explicit budget.timeout_seconds.
    # When a task DOES set budget.timeout_seconds, the executor polls until the
    # task reaches a terminal state or the deadline elapses (real tracking).
    socket_poll_interval_s: float = 0.5
    socket_max_polls: int = 1
    # Terminal-mode polling cap (read_state) for the same timeout-driven tracking.
    terminal_poll_interval_s: float = 0.5
    terminal_max_polls: int = 1
    # Account rotation on token exhaustion (doc 36 / ADR-009). Disabled by default
    # so it never changes startup behavior until explicitly enabled at deploy.
    rotation_enabled: bool = False
    rotation_login_timeout_s: float = 120.0
    rotation_max_rotations_per_window: int = 8
    rotation_logout_commands_json: str | None = None
    llm_gateway_base_url: str | None = None
    llm_gateway_api_key: str | None = None
    llm_gateway_api_keys: tuple[str, ...] = ()
    llm_gateway_default_model: str | None = None
    llm_gateway_timeout_s: float = 60.0
    llm_gateway_cache_ttl_s: float = 0.0
    llm_gateway_quota_per_minute: int = 0
    security_rate_limit_enabled: bool = True
    security_rate_limit_requests: int = 300
    security_rate_limit_window_s: float = 60.0
    security_rate_limit_exempt_paths: tuple[str, ...] = ("/health", "/health/ready", "/metrics")
    security_waf_enabled: bool = True
    security_waf_max_body_bytes: int = 1_048_576
    otel_enabled: bool = False
    otel_service_name: str = "aop-control-plane"
    otel_exporter_otlp_endpoint: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            redis_url=os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
            host=os.environ.get("AOP_HOST", "127.0.0.1"),
            port=int(os.environ.get("AOP_PORT", "8090")),
            cors_origins=_cors_origins_from_env(),
            seats_json=os.environ.get("AOP_SEATS_JSON"),
            seats_file=os.environ.get("AOP_SEATS_FILE"),
            device_login_commands_json=os.environ.get("AOP_DEVICE_LOGIN_COMMANDS_JSON"),
            herdmaster_url=os.environ.get("HERDMASTER_URL", "http://127.0.0.1:8080"),
            herdmaster_token=os.environ.get("HERDMASTER_TOKEN") or None,
            herdr_socket_path=os.environ.get("HERDR_SOCKET_PATH") or None,
            socket_poll_interval_s=float(os.environ.get("AOP_SOCKET_POLL_INTERVAL_S", "0.5")),
            socket_max_polls=int(os.environ.get("AOP_SOCKET_MAX_POLLS", "1")),
            terminal_poll_interval_s=float(os.environ.get("AOP_TERMINAL_POLL_INTERVAL_S", "0.5")),
            terminal_max_polls=int(os.environ.get("AOP_TERMINAL_MAX_POLLS", "1")),
            rotation_enabled=os.environ.get("AOP_ROTATION_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            rotation_login_timeout_s=float(os.environ.get("AOP_ROTATION_LOGIN_TIMEOUT_S", "120")),
            rotation_max_rotations_per_window=int(os.environ.get("AOP_ROTATION_MAX_PER_WINDOW", "8")),
            rotation_logout_commands_json=os.environ.get("AOP_LOGOUT_COMMANDS_JSON"),
            llm_gateway_base_url=os.environ.get("AOP_LLM_GATEWAY_BASE_URL") or None,
            llm_gateway_api_key=os.environ.get("AOP_LLM_GATEWAY_API_KEY") or None,
            llm_gateway_api_keys=_csv_env("AOP_LLM_GATEWAY_API_KEYS", ()),
            llm_gateway_default_model=os.environ.get("AOP_LLM_GATEWAY_DEFAULT_MODEL") or None,
            llm_gateway_timeout_s=float(os.environ.get("AOP_LLM_GATEWAY_TIMEOUT_S", "60")),
            llm_gateway_cache_ttl_s=float(os.environ.get("AOP_LLM_GATEWAY_CACHE_TTL_S", "0")),
            llm_gateway_quota_per_minute=int(os.environ.get("AOP_LLM_GATEWAY_QUOTA_PER_MINUTE", "0")),
            security_rate_limit_enabled=_bool_env("AOP_SECURITY_RATE_LIMIT_ENABLED", True),
            security_rate_limit_requests=int(os.environ.get("AOP_SECURITY_RATE_LIMIT_REQUESTS", "300")),
            security_rate_limit_window_s=float(os.environ.get("AOP_SECURITY_RATE_LIMIT_WINDOW_S", "60")),
            security_rate_limit_exempt_paths=_csv_env(
                "AOP_SECURITY_RATE_LIMIT_EXEMPT_PATHS",
                ("/health", "/health/ready", "/metrics"),
            ),
            security_waf_enabled=_bool_env("AOP_SECURITY_WAF_ENABLED", True),
            security_waf_max_body_bytes=int(os.environ.get("AOP_SECURITY_WAF_MAX_BODY_BYTES", "1048576")),
            otel_enabled=_bool_env("AOP_OTEL_ENABLED", False),
            otel_service_name=os.environ.get("AOP_OTEL_SERVICE_NAME", "aop-control-plane"),
            otel_exporter_otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        )


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or default


def _cors_origins_from_env() -> tuple[str, ...]:
    origins = _csv_env("AOP_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    if "*" in origins:
        raise ValueError("AOP_CORS_ORIGINS cannot contain '*' while credentials are enabled")
    return origins


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}

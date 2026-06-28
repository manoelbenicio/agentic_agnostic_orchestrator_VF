"""Dependency wiring for the integrated control-plane app."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tomllib
from contextlib import suppress
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import psycopg
import redis
from psycopg.pq import TransactionStatus
from psycopg import sql
from psycopg.rows import dict_row

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover - startup path reports the missing dependency
    ConnectionPool = None  # type: ignore[assignment,misc]

from coupling import CouplingStatus, build_coupled_executors
from core import (
    AdapterMetering,
    AgentState,
    OperationMode,
    RuntimeRef,
    TaskEnvelope,
)
from executors import SocketExecutor, TerminalExecutor, build_mode_router
from finops import FinOpsEngine, FinOpsRepository, record_event_costs
from finops.schema import _schema_name as finops_schema_name
from finops.schema import init_schema as init_finops_schema
from inbox_api import InboxRepository
from inbox_api.schema import _schema_name as inbox_schema_name
from inbox_api.schema import init_schema as init_inbox_schema
from issues_api import IssueRepository
from issues_api.schema import _schema_name as issues_schema_name
from issues_api.schema import init_schema as init_issues_schema
from projects_api import ProjectRepository
from projects_api.schema import _schema_name as projects_schema_name
from projects_api.schema import init_schema as init_projects_schema
from settings_api import SettingsRepository
from settings_api.schema import _schema_name as settings_schema_name
from settings_api.schema import init_schema as init_settings_schema
from registry import AgentRegistryRepository, AgentRegistryService, CompositePropagationHook
from registry.schema import _schema_name as registry_schema_name
from registry.schema import init_schema as init_registry_schema
from scheduler import QuotaAwareScheduler, QuotaLedger
from seats.pool import Seat, SeatPool
from seats_api import SeatsRepository
from seats_api.schema import _schema_name as seats_api_schema_name
from seats_api.schema import init_schema as init_seats_api_schema
from sessions_api import DeviceLoginService, SessionsRepository
from sessions_api.schema import _schema_name as sessions_api_schema_name
from sessions_api.schema import init_schema as init_sessions_api_schema
from sessions_api.service import provider_commands_from_json
from tasks_api import TaskRepository, TaskReconciler
from tasks_api.schema import _schema_name as tasks_api_schema_name
from tasks_api.schema import init_schema as init_tasks_api_schema
from topology.mapper import CanvasEdge, CanvasNode, TopologyMapper
from topology.repository import TopologyRepository
from tracing import TraceRepository, TraceService
from tracing.schema import _schema_name as tracing_schema_name
from tracing.schema import init_schema as init_tracing_schema

from .settings import Settings
from .provisioning import init_schema as init_provisioning_schema
from .audit import AuditRepository
from .audit import init_schema as init_audit_schema


logger = logging.getLogger(__name__)


class DegradedQueueClient:
    """Queue client used only to fail visibly when HerdMaster is unavailable."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def enqueue(self, task: TaskEnvelope) -> Mapping[str, Any]:
        raise RuntimeError(f"socket runtime unavailable: {self.reason}")

    async def claim(self, task: TaskEnvelope) -> Mapping[str, Any]:
        raise RuntimeError(f"socket runtime unavailable: {self.reason}")

    async def mark_running(self, task: TaskEnvelope) -> Mapping[str, Any]:
        raise RuntimeError(f"socket runtime unavailable: {self.reason}")

    async def poll(self, task: TaskEnvelope) -> Mapping[str, Any]:
        raise RuntimeError(f"socket runtime unavailable: {self.reason}")


class DegradedRuntimeAdapter:
    """Terminal adapter used only to fail visibly when Herdr is unavailable."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def spawn(self, task: TaskEnvelope) -> RuntimeRef:
        raise RuntimeError(f"terminal runtime unavailable: {self.reason}")

    async def send(self, runtime: RuntimeRef, payload: str) -> None:
        raise RuntimeError(f"terminal runtime unavailable: {self.reason}")

    async def read_state(self, runtime: RuntimeRef) -> AgentState:
        raise RuntimeError(f"terminal runtime unavailable: {self.reason}")

    async def stop(self, runtime: RuntimeRef) -> None:
        raise RuntimeError(f"terminal runtime unavailable: {self.reason}")

    async def restore(self, runtime: RuntimeRef) -> RuntimeRef:
        raise RuntimeError(f"terminal runtime unavailable: {self.reason}")

    async def meter(
        self,
        runtime: RuntimeRef,
        usage_hint: Mapping[str, Any] | None = None,
    ) -> AdapterMetering:
        raise RuntimeError(f"terminal runtime unavailable: {self.reason}")


@dataclass(slots=True)
class AppState:
    """Stateful dependency container for the integrated API."""

    settings: Settings
    registry_repo: AgentRegistryRepository
    registry_service: AgentRegistryService
    audit_repo: AuditRepository
    finops_repo: FinOpsRepository
    finops_engine: FinOpsEngine
    trace_repo: TraceRepository
    trace_service: TraceService
    projects_repo: ProjectRepository
    inbox_repo: InboxRepository
    issues_repo: IssueRepository
    settings_repo: SettingsRepository
    topology_repo: TopologyRepository
    tasks_repo: TaskRepository
    tasks_reconciler: TaskReconciler
    seats_repo: SeatsRepository
    sessions_repo: SessionsRepository
    session_service: DeviceLoginService
    seat_pool: SeatPool
    scheduler: QuotaAwareScheduler
    mode_router: Any
    coupling_status: CouplingStatus
    redis_client: redis.Redis
    rotation_service: Any | None = None
    message_bus: Any | None = None
    message_bus_status: dict[str, str | None] = field(default_factory=dict)
    postgres_connections: list[Any] = field(default_factory=list)
    postgres_pools: list[Any] = field(default_factory=list)

    def close(self) -> None:
        for conn in self.postgres_connections:
            try:
                conn.rollback()
            except Exception:
                logger.warning("failed to rollback Postgres connection during shutdown", exc_info=True)
            try:
                conn.close()
            except Exception:
                logger.warning("failed to close Postgres connection during shutdown", exc_info=True)
        for pool in self.postgres_pools:
            pool.close()
        self.redis_client.close()


def build_state(settings: Settings | None = None) -> AppState:
    """Build and initialize all control-plane module dependencies."""
    settings = settings or Settings.from_env()

    registry_pool, registry_conn = _pooled_connection(
        settings.database_url,
        schema_name=registry_schema_name(),
        init_schema=init_registry_schema,
    )
    finops_pool, finops_conn = _pooled_connection(
        settings.database_url,
        schema_name=finops_schema_name(),
        init_schema=init_finops_schema,
    )
    tracing_pool, tracing_conn = _pooled_connection(
        settings.database_url,
        schema_name=tracing_schema_name(),
        init_schema=init_tracing_schema,
    )
    projects_pool, projects_conn = _pooled_connection(
        settings.database_url,
        schema_name=projects_schema_name(),
        init_schema=init_projects_schema,
    )
    issues_pool, issues_conn = _pooled_connection(
        settings.database_url,
        schema_name=issues_schema_name(),
        init_schema=init_issues_schema,
    )
    inbox_pool, inbox_conn = _pooled_connection(
        settings.database_url,
        schema_name=inbox_schema_name(),
        init_schema=init_inbox_schema,
    )
    settings_pool, settings_conn = _pooled_connection(
        settings.database_url,
        schema_name=settings_schema_name(),
        init_schema=init_settings_schema,
    )
    seats_api_pool, seats_api_conn = _pooled_connection(
        settings.database_url,
        schema_name=seats_api_schema_name(),
        init_schema=lambda conn: init_seats_api_schema(conn, schema_name=seats_api_schema_name()),
    )
    sessions_api_pool, sessions_api_conn = _pooled_connection(
        settings.database_url,
        schema_name=sessions_api_schema_name(),
        init_schema=lambda conn: init_sessions_api_schema(conn, schema_name=sessions_api_schema_name()),
    )
    tasks_api_pool, tasks_api_conn = _pooled_connection(
        settings.database_url,
        schema_name=tasks_api_schema_name(),
        init_schema=init_tasks_api_schema,
    )
    provisioning_pool, provisioning_conn = _pooled_connection(
        settings.database_url,
        schema_name=os.environ.get("AOP_PROVISIONING_SCHEMA") or "aop_provisioning",
        init_schema=init_provisioning_schema,
    )
    audit_pool, audit_conn = _pooled_connection(
        settings.database_url,
        schema_name="aop_audit",
        init_schema=init_audit_schema,
    )

    registry_repo = AgentRegistryRepository(registry_conn)
    registry_service = AgentRegistryService(
        repository=registry_repo,
        propagation=CompositePropagationHook.default(),
        enrolled_workspaces={"default", "workspace-main"},
    )
    audit_repo = AuditRepository(audit_conn)
    finops_repo = FinOpsRepository(finops_conn)
    trace_repo = TraceRepository(tracing_conn)
    projects_repo = ProjectRepository(projects_conn)
    issues_repo = IssueRepository(issues_conn)
    settings_repo = SettingsRepository(settings_conn)
    inbox_repo = InboxRepository(inbox_conn)
    seats_repo = SeatsRepository(seats_api_conn)
    sessions_repo = SessionsRepository(sessions_api_conn)
    tasks_repo = TaskRepository(tasks_api_conn)
    tasks_reconciler = TaskReconciler(
        tasks_repo,
        squad_tasks_path=Path(__file__).parent.parent.parent / "ops" / "squad-tasks.json",
    )

    redis_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)

    seat_pool = _load_seat_pool(settings)
    for seat in seats_repo.list():
        seat_pool.register_seat(
            Seat(
                seat_id=seat.seat_id,
                tenant_id=seat.tenant_id,
                vendor=seat.vendor,
                home_dir=seat.home_dir,
            )
        )
    session_service = DeviceLoginService(
        seats_repo,
        sessions_repo,
        provider_commands=provider_commands_from_json(settings.device_login_commands_json),
    )

    live_herdmaster_token, _token_error = _resolve_herdmaster_token(settings)
    if live_herdmaster_token and live_herdmaster_token != settings.herdmaster_token:
        settings = replace(settings, herdmaster_token=live_herdmaster_token)

    coupled = build_coupled_executors(
        fallback_terminal_adapter=DegradedRuntimeAdapter("Herdr socket unavailable"),
        fallback_queue_client=DegradedQueueClient("HerdMaster HTTP unavailable"),
        herdmaster_url=settings.herdmaster_url,
        herdmaster_token=settings.herdmaster_token,
        herdr_socket_path=settings.herdr_socket_path,
        socket_poll_interval_s=settings.socket_poll_interval_s,
        socket_max_polls=settings.socket_max_polls,
    )
    message_bus, message_bus_status = _build_message_bus(settings)

    rotation_service = _build_rotation_service(settings, session_service)

    return AppState(
        settings=settings,
        registry_repo=registry_repo,
        registry_service=registry_service,
        audit_repo=audit_repo,
        finops_repo=finops_repo,
        finops_engine=FinOpsEngine(finops_repo),
        trace_repo=trace_repo,
        trace_service=TraceService(trace_repo),
        projects_repo=projects_repo,
        inbox_repo=inbox_repo,
        issues_repo=issues_repo,
        settings_repo=settings_repo,
        topology_repo=TopologyRepository(settings.database_url),
        tasks_repo=tasks_repo,
        tasks_reconciler=tasks_reconciler,
        seats_repo=seats_repo,
        sessions_repo=sessions_repo,
        session_service=session_service,
        seat_pool=seat_pool,
        scheduler=QuotaAwareScheduler(QuotaLedger(redis_client=redis_client)),
        mode_router=build_mode_router(coupled.terminal, coupled.socket),
        coupling_status=coupled.status,
        redis_client=redis_client,
        rotation_service=rotation_service,
        message_bus=message_bus,
        message_bus_status=message_bus_status,
        postgres_connections=[
            registry_conn,
            finops_conn,
            tracing_conn,
            projects_conn,
            issues_conn,
            inbox_conn,
            settings_conn,
            seats_api_conn,
            sessions_api_conn,
            tasks_api_conn,
            provisioning_conn,
            audit_conn,
        ],
        postgres_pools=[
            registry_pool,
            finops_pool,
            tracing_pool,
            projects_pool,
            issues_pool,
            inbox_pool,
            settings_pool,
            seats_api_pool,
            sessions_api_pool,
            tasks_api_pool,
            provisioning_pool,
            audit_pool,
        ],
    )


def _pool_reset(conn: psycopg.Connection[Any]) -> None:
    """Clean a connection before it is reused by the pool."""
    try:
        conn.rollback()
        conn.execute("DISCARD TEMP")
        conn.execute("RESET ALL")
        conn.commit()
    except Exception:
        logger.warning("control-plane DB pool reset failed; discarding connection", exc_info=True)
        raise


def _pool_reconnect_failed(pool: Any) -> None:
    """Log a critical alert when psycopg_pool exhausts reconnect attempts."""
    logger.critical(
        "control-plane DB pool reconnect FAILED after timeout; stats=%s",
        pool.get_stats() if hasattr(pool, "get_stats") else "unavailable",
    )


class _ResilientCursor:
    """Cursor proxy that rolls back the owning connection after psycopg errors."""

    def __init__(self, owner: "_ResilientPooledConnection", cursor: Any) -> None:
        self._owner = owner
        self._cursor = cursor

    def __enter__(self) -> "_ResilientCursor":
        self._cursor.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        try:
            if exc_type is not None and issubclass(exc_type, psycopg.Error):
                self._owner.rollback_after_error()
        finally:
            return self._cursor.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._cursor.execute(*args, **kwargs)
        except psycopg.OperationalError:
            self._owner.rollback_after_error()
            self._cursor = self._owner._ensure_connection().cursor()
            return self._cursor.execute(*args, **kwargs)
        except psycopg.Error:
            self._owner.rollback_after_error()
            raise

    def executemany(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._cursor.executemany(*args, **kwargs)
        except psycopg.OperationalError:
            self._owner.rollback_after_error()
            self._cursor = self._owner._ensure_connection().cursor()
            return self._cursor.executemany(*args, **kwargs)
        except psycopg.Error:
            self._owner.rollback_after_error()
            raise


class _ResilientPooledConnection:
    """Long-lived repository connection backed by a checked psycopg pool."""

    def __init__(self, pool: Any, conn: psycopg.Connection[Any], schema_name: str) -> None:
        self._pool = pool
        self._conn: psycopg.Connection[Any] | None = conn
        self._schema_name = schema_name
        self._returned = False

    def _ensure_connection(self) -> psycopg.Connection[Any]:
        if self._returned:
            raise psycopg.OperationalError("Postgres pooled connection was already returned")
        if self._conn is None or self._conn.closed:
            self._conn = self._pool.getconn()
            self._prepare_connection(self._conn)
            return self._conn
        try:
            self._check_connection(self._conn)
        except Exception:
            logger.warning(
                "control-plane DB pooled connection failed health check; reconnecting schema=%s",
                self._schema_name,
                exc_info=True,
            )
            stale = self._conn
            with suppress(Exception):
                stale.close()
            with suppress(Exception):
                self._pool.putconn(stale)
            self._conn = self._pool.getconn()
            self._prepare_connection(self._conn)
        return self._conn

    def _check_connection(self, conn: psycopg.Connection[Any]) -> None:
        if conn.pgconn.transaction_status != TransactionStatus.IDLE:
            return
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        self._prepare_connection(conn)

    def _prepare_connection(self, conn: psycopg.Connection[Any]) -> None:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self._schema_name)))
        conn.commit()

    def cursor(self, *args: Any, **kwargs: Any) -> _ResilientCursor:
        conn = self._ensure_connection()
        return _ResilientCursor(self, conn.cursor(*args, **kwargs))

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        conn = self._ensure_connection()
        try:
            return conn.execute(*args, **kwargs)
        except psycopg.OperationalError:
            self.rollback_after_error()
            conn = self._ensure_connection()
            return conn.execute(*args, **kwargs)
        except psycopg.Error:
            self.rollback_after_error()
            raise

    def commit(self) -> None:
        conn = self._ensure_connection()
        try:
            conn.commit()
        except psycopg.Error:
            self.rollback_after_error()
            raise

    def rollback(self) -> None:
        if self._returned or self._conn is None:
            return
        self._conn.rollback()

    def rollback_after_error(self) -> None:
        if self._returned or self._conn is None:
            return
        try:
            self._conn.rollback()
        except psycopg.Error:
            logger.warning(
                "control-plane DB rollback failed after psycopg error; reconnecting schema=%s",
                self._schema_name,
                exc_info=True,
            )
            stale = self._conn
            with suppress(Exception):
                stale.close()
            with suppress(Exception):
                self._pool.putconn(stale)
            self._conn = self._pool.getconn()

    def close(self) -> None:
        if self._returned:
            return
        self._returned = True
        if self._conn is None:
            return
        conn = self._conn
        self._conn = None
        with suppress(Exception):
            conn.rollback()
        self._pool.putconn(conn)


def _pooled_connection(
    database_url: str,
    *,
    schema_name: str,
    init_schema: Any,
) -> tuple[Any, _ResilientPooledConnection]:
    """Create a checked psycopg pool, wait for readiness, and return one connection."""
    if ConnectionPool is None:
        raise ImportError("psycopg_pool is required for AOP DB pooling; install psycopg-pool")

    def _configure(conn: psycopg.Connection[Any]) -> None:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))
        conn.commit()

    pool = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=4,
        timeout=30.0,
        reconnect_timeout=300.0,
        open=True,
        check=ConnectionPool.check_connection,
        reset=_pool_reset,
        reconnect_failed=_pool_reconnect_failed,
        configure=_configure,
        kwargs={"row_factory": dict_row},
    )
    pool.wait(timeout=30.0)
    conn = pool.getconn()
    try:
        ConnectionPool.check_connection(conn)
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema_name)))
            cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema_name)))
        conn.commit()
        init_schema(conn)
    except Exception:
        conn.rollback()
        pool.putconn(conn)
        pool.close()
        raise
    resilient_conn = _ResilientPooledConnection(pool, conn, schema_name)
    logger.info("control-plane DB pool ready for schema %s; stats=%s", schema_name, pool.get_stats())
    return pool, resilient_conn


def _load_seat_pool(settings: Settings) -> SeatPool:
    """Load seats from explicit production config only.

    Supported sources are ``AOP_SEATS_JSON`` or ``AOP_SEATS_FILE``.  A file may
    be JSON or TOML with ``[[seats]]`` entries.  If neither source is configured,
    the pool is intentionally empty.
    """
    pool = SeatPool()
    for raw in _seat_records(settings):
        pool.register_seat(
            Seat(
                seat_id=str(raw["seat_id"]),
                tenant_id=str(raw["tenant_id"]),
                vendor=str(raw["vendor"]),
                home_dir=str(raw["home_dir"]),
                token_lifetime=float(raw.get("token_lifetime", 3600.0)),
                token=str(raw["token"]) if raw.get("token") else None,
            )
        )
    return pool


def _seat_records(settings: Settings) -> list[dict[str, Any]]:
    if settings.seats_json:
        decoded = json.loads(settings.seats_json)
    elif settings.seats_file:
        path = Path(settings.seats_file)
        text = path.read_text(encoding="utf-8")
        decoded = tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)
    else:
        return []
    records = decoded.get("seats", decoded) if isinstance(decoded, dict) else decoded
    if not isinstance(records, list):
        raise ValueError("seat config must be a list or an object containing seats=[]")
    required = {"seat_id", "tenant_id", "vendor", "home_dir"}
    for record in records:
        if not isinstance(record, dict) or not required.issubset(record):
            raise ValueError("each seat requires seat_id, tenant_id, vendor, and home_dir")
    return records


def _build_rotation_service(settings: Settings, session_service: DeviceLoginService) -> Any | None:
    """Build the account-rotation service when AOP_ROTATION_ENABLED is set.

    Disabled by default so startup behavior is unchanged. Never raises on
    misconfiguration — logs and returns None so the control plane still boots.
    """
    if not settings.rotation_enabled:
        return None
    try:
        from rotation import build_rotation_service

        records = _seat_records(settings)
        if not records:
            logger.warning("rotation enabled but no seat/account records configured; rotation disabled")
            return None
        logout_commands = (
            json.loads(settings.rotation_logout_commands_json)
            if settings.rotation_logout_commands_json
            else None
        )
        return build_rotation_service(
            records,
            session_service,
            logout_commands=logout_commands,
            login_timeout_s=settings.rotation_login_timeout_s,
            max_rotations_per_window=settings.rotation_max_rotations_per_window,
        )
    except Exception:
        logger.warning("failed to build rotation service; continuing without it", exc_info=True)
        return None


def _build_message_bus(settings: Settings) -> tuple[Any | None, dict[str, str | None]]:
    from messaging import HerdMasterHttpMessageBus

    token, token_error = _resolve_herdmaster_token(settings)
    if not token:
        return None, {"status": "degraded", "last_error": token_error or "HerdMaster message bus token is not configured"}
    try:
        return (
            HerdMasterHttpMessageBus(base_url=settings.herdmaster_url, token=token),
            {"status": "connected", "last_error": None},
        )
    except Exception as exc:
        logger.warning("HerdMaster message bus initialization failed; degrading gracefully", exc_info=True)
        return None, {"status": "degraded", "last_error": f"HerdMaster message bus init failed: {exc}"}


def _resolve_herdmaster_token(settings: Settings) -> tuple[str | None, str | None]:
    """Return a HerdMaster token that is accepted by the live HTTP API.

    Long-lived control-plane processes can keep an old HERDMASTER_TOKEN after
    ops/start.sh rotates HerdMaster's runtime token. Probe candidates in order
    and prefer the first token that authenticates against the configured URL.
    """
    from coupling.hm_client import herdmaster_authenticated_probe

    last_error: str | None = None
    for source, token in _herdmaster_token_candidates(settings):
        if not token:
            continue
        try:
            if herdmaster_authenticated_probe(settings.herdmaster_url, token=token):
                if source != "settings.herdmaster_token":
                    logger.info("resolved live HerdMaster token from %s", source)
                return token, None
            last_error = f"HerdMaster message bus is unavailable for token source {source}"
        except Exception as exc:
            logger.warning("HerdMaster token probe failed for %s; trying next candidate", source, exc_info=True)
            last_error = f"HerdMaster message bus probe failed: {exc}"
    return None, last_error or "HerdMaster message bus token is not configured"


def _herdmaster_token_candidates(settings: Settings) -> list[tuple[str, str | None]]:
    candidates: list[tuple[str, str | None]] = [("settings.herdmaster_token", settings.herdmaster_token)]
    token_file = os.environ.get("AOP_HERDMASTER_TOKEN_FILE")
    runtime_dir = os.environ.get("AOP_OPS_RUNTIME_DIR")
    paths = [
        Path(token_file) if token_file else None,
        Path(runtime_dir) / "herdmaster.token" if runtime_dir else None,
        Path.home() / ".aop-runtime" / "herdmaster.token",
        Path("/tmp/aop-ops-runtime-user/herdmaster.token"),
    ]
    seen: set[str] = set()
    for path in paths:
        if path is None:
            continue
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        token = _read_token_file(path)
        candidates.append((f"file:{key}", token))
    return candidates


def _read_token_file(path: Path) -> str | None:
    try:
        token = path.expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def refresh_message_bus(state: AppState) -> dict[str, str | None]:
    """Re-evaluate the HerdMaster message bus without breaking health checks.

    This is intentionally graceful: transient HerdMaster HTTP failures clear the
    live bus and mark it degraded; a later healthy probe reconstructs the bus.
    """
    message_bus, message_bus_status = _build_message_bus(state.settings)
    state.message_bus = message_bus
    state.message_bus_status = message_bus_status
    return message_bus_status


_QUOTA_DETECTOR: Any | None = None


def _quota_detector() -> Any:
    """Lazily build and cache the quota-exhaustion detector (reads env patterns)."""
    global _QUOTA_DETECTOR
    if _QUOTA_DETECTOR is None:
        from rotation import QuotaExhaustionDetector

        _QUOTA_DETECTOR = QuotaExhaustionDetector()
    return _QUOTA_DETECTOR


async def collect_events(task: TaskEnvelope, state: AppState) -> list[dict[str, Any]]:
    """Dispatch through ModeRouter, serialize events, feed FinOps, and rotate.

    Per event, any ``finops`` payload in the details is recorded automatically
    (self-fed FinOps). When account rotation is enabled (``state.rotation_service``)
    and the task carries ``account_id``, a token-exhaustion signal detected in the
    events triggers a rotation to the next account (by expertise priority) and the
    task is re-dispatched (restart) on the new account — bounded to avoid thrash.
    With rotation disabled (default) this behaves exactly like a single dispatch.
    """
    issue_id = task.issue_id or "issue-default"
    agent_id = task.agent_id or task.assignee_runtime
    events: list[dict[str, Any]] = []

    async def _run_dispatch(current: TaskEnvelope) -> Any:
        """Dispatch once; feed FinOps; return an exhaustion signal or None."""
        executor = state.mode_router.route(current)
        rotation_on = state.rotation_service is not None and current.account_id
        detector = _quota_detector() if rotation_on else None
        signal = None
        async for event in executor.dispatch(current):
            payload = event.model_dump(mode="json")
            events.append(payload)
            try:
                record_event_costs(
                    state.finops_engine,
                    tenant_id=current.tenant_id,
                    project_id=current.project_id,
                    issue_id=issue_id,
                    agent_id=agent_id,
                    runtime_id=event.runtime,
                    trace_id=event.trace_id,
                    details=event.details,
                )
            except Exception:  # pragma: no cover - dispatch must not break on FinOps
                logger.warning("FinOps bridge failed for task %s event %s", current.task_id, event.status, exc_info=True)
            if detector is not None and signal is None:
                from rotation import exhaustion_from_event

                candidate = exhaustion_from_event(detector, payload)
                if candidate.exhausted:
                    signal = candidate
        return signal

    current_task = task
    signal = await _run_dispatch(current_task)

    # Rotation + resume loop (only when enabled and an account is mapped).
    if state.rotation_service is not None and task.account_id:
        max_resumes = max(1, getattr(state.settings, "rotation_max_rotations_per_window", 8))
        attempts = 0
        while signal is not None and signal.exhausted and attempts < max_resumes:
            attempts += 1
            try:
                outcome = _attempt_rotation(state, current_task, signal, agent_id, issue_id)
            except Exception:  # pragma: no cover - rotation must never break dispatch
                logger.warning("rotation attempt failed for task %s", current_task.task_id, exc_info=True)
                break
            events.append(_rotation_marker_event(current_task, outcome))
            if not outcome.rotated or not outcome.to_account:
                break  # parked or failed → stop; quota will resume at reset
            # Resume = restart the same task on the new account (context not portable).
            current_task = current_task.model_copy(update={"account_id": outcome.to_account})
            signal = await _run_dispatch(current_task)

    return events


def _attempt_rotation(state: AppState, task: TaskEnvelope, signal: Any, agent_id: str, issue_id: str) -> Any:
    """Call the rotation service for one exhaustion signal; return the RotationOutcome."""
    from datetime import datetime, timezone

    from rotation import RotationReason, TaskSnapshot

    now = datetime.now(timezone.utc)
    cooldown_until = None
    try:
        cooldown_until = _quota_detector().parse_reset_time(getattr(signal, "reset_hint", None), now=now)
    except Exception:  # parsing is best-effort; fall back to window default
        cooldown_until = None
    snapshot = TaskSnapshot(task_id=task.task_id, prompt=task.prompt, metadata={"issue_id": issue_id})
    return state.rotation_service.on_exhaustion(
        agent_id=agent_id,
        tenant_id=task.tenant_id,
        current_account_id=task.account_id,
        snapshot=snapshot,
        reason=RotationReason.QUOTA_EXHAUSTED_REACTIVE,
        cooldown_until=cooldown_until,
        vendor=getattr(signal, "vendor", None) or None,
        now=now,
    )


def _rotation_marker_event(task: TaskEnvelope, outcome: Any) -> dict[str, Any]:
    """A synthetic event documenting a rotation attempt in the task's event stream."""
    from datetime import datetime, timezone

    return {
        "event_id": f"rotation-{task.task_id}-{datetime.now(timezone.utc).timestamp()}",
        "task_id": task.task_id,
        "tenant_id": task.tenant_id,
        "project_id": task.project_id,
        "status": "rotated" if getattr(outcome, "rotated", False) else "parked",
        "operation_mode": task.operation_mode.value,
        "runtime": task.assignee_runtime,
        "message": (
            f"account rotation: from={getattr(outcome, 'from_account', None)} "
            f"to={getattr(outcome, 'to_account', None)} parked={getattr(outcome, 'parked', False)} "
            f"error={getattr(outcome, 'error', None)}"
        ),
        "details": {
            "rotation": {
                "rotated": getattr(outcome, "rotated", False),
                "from_account": getattr(outcome, "from_account", None),
                "to_account": getattr(outcome, "to_account", None),
                "parked": getattr(outcome, "parked", False),
                "wake_at": getattr(outcome, "wake_at", None).isoformat() if getattr(outcome, "wake_at", None) else None,
                "error": getattr(outcome, "error", None),
            }
        },
    }


def map_topology(nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> Any:
    """Convert canvas JSON into HerdMaster ACL config using topology mapper."""
    canvas_nodes, canvas_edges = canvas_topology(nodes, edges)
    return TopologyMapper.map_to_acl(canvas_nodes, canvas_edges)


def canvas_topology(
    nodes: list[dict[str, str]],
    edges: list[dict[str, str]],
) -> tuple[list[CanvasNode], list[CanvasEdge]]:
    """Convert canvas JSON into topology dataclasses."""
    canvas_nodes = [CanvasNode(id=item["id"], role=item["role"]) for item in nodes]
    canvas_edges = [CanvasEdge(source=item["source"], target=item["target"]) for item in edges]
    return canvas_nodes, canvas_edges


async def close_state(state: AppState) -> None:
    await asyncio.to_thread(state.close)

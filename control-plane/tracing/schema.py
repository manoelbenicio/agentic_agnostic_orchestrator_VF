"""Postgres schema helpers for tracing."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

DEFAULT_DATABASE_URL = "postgresql://aop_dev:aop_dev_postgres_20260626@127.0.0.1:5432/aop"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trace_events (
    event_id      TEXT PRIMARY KEY,
    trace_id      TEXT NOT NULL,
    layer         TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    tenant_id     TEXT NOT NULL,
    project_id    TEXT NOT NULL,
    issue_id      TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    runtime_id    TEXT NOT NULL,
    message       TEXT NOT NULL,
    token_burn    INTEGER NOT NULL DEFAULT 0,
    seat_seconds  INTEGER NOT NULL DEFAULT 0,
    details       JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trace_session_artifacts (
    trace_id      TEXT NOT NULL,
    artifact_uri  TEXT NOT NULL,
    runtime_id    TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trace_id, artifact_uri)
);

CREATE INDEX IF NOT EXISTS idx_trace_events_trace
    ON trace_events(trace_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_trace_events_agent
    ON trace_events(agent_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_trace_events_runtime
    ON trace_events(runtime_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_trace_events_burn
    ON trace_events(agent_id, runtime_id, signal_type);
CREATE INDEX IF NOT EXISTS idx_trace_session_artifacts_trace_created
    ON trace_session_artifacts(trace_id, created_at ASC, artifact_uri ASC);
CREATE INDEX IF NOT EXISTS idx_trace_events_agent_runtime_burn
    ON trace_events(agent_id, runtime_id)
    INCLUDE (token_burn, seat_seconds);
"""


def _database_url(database_url: str | None = None) -> str:
    return database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _schema_name(name: str | None = None, *, seed: str | Path | None = None) -> str:
    if name:
        candidate = name
    elif os.environ.get("AOP_TRACING_SCHEMA"):
        candidate = os.environ["AOP_TRACING_SCHEMA"]
    else:
        source = str(seed or "aop_tracing")
        candidate = "aop_tracing_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate


def connect(
    *,
    database_url: str | None = None,
    schema_name: str | None = None,
    schema_seed: str | Path | None = None,
) -> psycopg.Connection[Any]:
    """Open a Postgres connection with search_path set to the tracing schema."""
    schema = _schema_name(schema_name, seed=schema_seed)
    conn = psycopg.connect(_database_url(database_url), row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    conn.commit()
    return conn


def init_schema(conn: psycopg.Connection[Any]) -> None:
    """Create tracing tables and indexes idempotently."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()

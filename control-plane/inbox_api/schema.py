"""Postgres connection and schema helpers for inbox events."""

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
CREATE TABLE IF NOT EXISTS inbox_events (
    id           TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    type         TEXT NOT NULL DEFAULT 'info',
    title        TEXT NOT NULL,
    message      TEXT NOT NULL DEFAULT '',
    read         BOOLEAN NOT NULL DEFAULT FALSE,
    archived     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inbox_events_tenant_read
    ON inbox_events(tenant_id, read)
    WHERE archived = FALSE;

CREATE INDEX IF NOT EXISTS idx_inbox_events_created_at
    ON inbox_events(created_at DESC)
    WHERE archived = FALSE;

CREATE INDEX IF NOT EXISTS idx_inbox_events_tenant_created
    ON inbox_events(tenant_id, created_at DESC, id ASC)
    WHERE archived = FALSE;

CREATE INDEX IF NOT EXISTS idx_inbox_events_tenant_read_created
    ON inbox_events(tenant_id, read, created_at DESC, id ASC)
    WHERE archived = FALSE;

CREATE INDEX IF NOT EXISTS idx_inbox_events_unread_tenant
    ON inbox_events(tenant_id)
    WHERE archived = FALSE AND read = FALSE;
"""


def _database_url(database_url: str | None = None) -> str:
    return database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _schema_name(name: str | None = None, *, seed: str | Path | None = None) -> str:
    if name:
        candidate = name
    elif os.environ.get("AOP_INBOX_SCHEMA"):
        candidate = os.environ["AOP_INBOX_SCHEMA"]
    else:
        source = str(seed or "aop_inbox")
        candidate = "aop_inbox_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate


def connect(
    *,
    database_url: str | None = None,
    schema_name: str | None = None,
    schema_seed: str | Path | None = None,
) -> psycopg.Connection[Any]:
    """Open a Postgres connection with search_path set to the inbox schema."""
    schema = _schema_name(schema_name, seed=schema_seed)
    conn = psycopg.connect(_database_url(database_url), row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    conn.commit()
    return conn


def init_schema(conn: psycopg.Connection[Any]) -> None:
    """Create the inbox_events table and indexes idempotently."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()

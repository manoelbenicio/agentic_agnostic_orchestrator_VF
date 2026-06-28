"""Postgres schema for vendor sessions."""

from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


DEFAULT_SCHEMA = "aop_sessions_api"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    seat_id         TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    vendor          TEXT NOT NULL,
    status          TEXT NOT NULL,
    status_reason   TEXT,
    verification_uri TEXT,
    user_code       TEXT,
    device_code_ref TEXT,
    expires_at      TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS sessions_seat_idx ON sessions (seat_id, created_at DESC);
CREATE INDEX IF NOT EXISTS sessions_tenant_vendor_created_idx ON sessions (tenant_id, vendor, created_at DESC);
CREATE INDEX IF NOT EXISTS sessions_status_created_idx ON sessions (status, created_at DESC);
CREATE INDEX IF NOT EXISTS sessions_active_seat_idx
    ON sessions (status, seat_id)
    WHERE status IN ('pending', 'authenticated');
"""


def connect(database_url: str, *, schema_name: str | None = None) -> psycopg.Connection[Any]:
    conn = psycopg.connect(database_url, row_factory=dict_row)
    set_search_path(conn, schema_name=schema_name)
    return conn


def init_schema(conn: psycopg.Connection[Any], *, schema_name: str | None = None) -> None:
    name = _schema_name(schema_name)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(name)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(name)))
        cur.execute(SCHEMA_SQL)
    conn.commit()


def set_search_path(conn: psycopg.Connection[Any], *, schema_name: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(_schema_name(schema_name))))


def _schema_name(name: str | None = None) -> str:
    candidate = name or os.environ.get("AOP_SESSIONS_API_SCHEMA") or DEFAULT_SCHEMA
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate

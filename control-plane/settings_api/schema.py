"""Postgres connection and schema helpers for settings."""

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
CREATE TABLE IF NOT EXISTS settings (
    setting_id   TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, key)
);

CREATE INDEX IF NOT EXISTS idx_settings_tenant
    ON settings(tenant_id);

CREATE TABLE IF NOT EXISTS api_tokens (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL,
    prefix      TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMPTZ,
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_tenant
    ON api_tokens(tenant_id)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_api_tokens_tenant_created
    ON api_tokens(tenant_id, created_at DESC, id ASC)
    WHERE revoked_at IS NULL;
"""


def _database_url(database_url: str | None = None) -> str:
    return database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _schema_name(name: str | None = None, *, seed: str | Path | None = None) -> str:
    if name:
        candidate = name
    elif os.environ.get("AOP_SETTINGS_SCHEMA"):
        candidate = os.environ["AOP_SETTINGS_SCHEMA"]
    else:
        source = str(seed or "aop_settings")
        candidate = "aop_settings_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate


def connect(
    *,
    database_url: str | None = None,
    schema_name: str | None = None,
    schema_seed: str | Path | None = None,
) -> psycopg.Connection[Any]:
    """Open a Postgres connection with search_path set to the settings schema."""
    schema = _schema_name(schema_name, seed=schema_seed)
    conn = psycopg.connect(_database_url(database_url), row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    conn.commit()
    return conn


def init_schema(conn: psycopg.Connection[Any]) -> None:
    """Create the settings and api_tokens tables idempotently."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        cur.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'api_tokens'
                      AND column_name = 'token_id'
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'api_tokens'
                      AND column_name = 'id'
                )
                THEN
                    ALTER TABLE api_tokens RENAME COLUMN token_id TO id;
                END IF;
            END $$;
            """
        )
    conn.commit()

"""Postgres connection and schema helpers for projects."""

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
CREATE TABLE IF NOT EXISTS projects (
    project_id   TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_projects_tenant_status
    ON projects(tenant_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_projects_created_at
    ON projects(created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_projects_tenant_created
    ON projects(tenant_id, created_at DESC, project_id ASC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_projects_tenant_status_created
    ON projects(tenant_id, status, created_at DESC, project_id ASC)
    WHERE deleted_at IS NULL;
"""


def _database_url(database_url: str | None = None) -> str:
    return database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _schema_name(name: str | None = None, *, seed: str | Path | None = None) -> str:
    if name:
        candidate = name
    elif os.environ.get("AOP_PROJECTS_SCHEMA"):
        candidate = os.environ["AOP_PROJECTS_SCHEMA"]
    else:
        source = str(seed or "aop_projects")
        candidate = "aop_projects_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate


def connect(
    *,
    database_url: str | None = None,
    schema_name: str | None = None,
    schema_seed: str | Path | None = None,
) -> psycopg.Connection[Any]:
    """Open a Postgres connection with search_path set to the projects schema."""
    schema = _schema_name(schema_name, seed=schema_seed)
    conn = psycopg.connect(_database_url(database_url), row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    conn.commit()
    return conn


def init_schema(conn: psycopg.Connection[Any]) -> None:
    """Create the projects table and indexes idempotently."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()

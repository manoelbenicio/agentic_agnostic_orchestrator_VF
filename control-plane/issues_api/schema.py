"""Postgres connection and schema helpers for issues."""

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
CREATE TABLE IF NOT EXISTS issues (
    issue_id         TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    title            TEXT NOT NULL,
    description      TEXT,
    status           TEXT NOT NULL DEFAULT 'backlog',
    priority         TEXT NOT NULL DEFAULT 'medium',
    assignee_runtime TEXT,
    operation_mode   TEXT NOT NULL DEFAULT 'terminal',
    due_date         DATE,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_issues_tenant_project_status
    ON issues(tenant_id, project_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_assignee
    ON issues(assignee_runtime)
    WHERE deleted_at IS NULL AND assignee_runtime IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_issues_tenant_project_created
    ON issues(tenant_id, project_id, created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_tenant_project_status_created
    ON issues(tenant_id, project_id, status, created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_assignee_created
    ON issues(assignee_runtime, created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL AND assignee_runtime IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_issues_assignee_pattern_created
    ON issues(assignee_runtime text_pattern_ops, created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL AND assignee_runtime IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_issues_metadata_created_by_created
    ON issues((metadata->>'created_by'), created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_metadata_created_by_agent_created
    ON issues((metadata->>'created_by_agent'), created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_metadata_owner_created
    ON issues((metadata->>'owner'), created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_metadata_reporter_created
    ON issues((metadata->>'reporter'), created_at DESC, issue_id ASC)
    WHERE deleted_at IS NULL;
"""


def _database_url(database_url: str | None = None) -> str:
    return database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _schema_name(name: str | None = None, *, seed: str | Path | None = None) -> str:
    if name:
        candidate = name
    elif os.environ.get("AOP_ISSUES_SCHEMA"):
        candidate = os.environ["AOP_ISSUES_SCHEMA"]
    else:
        source = str(seed or "aop_issues")
        candidate = "aop_issues_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate


def connect(
    *,
    database_url: str | None = None,
    schema_name: str | None = None,
    schema_seed: str | Path | None = None,
) -> psycopg.Connection[Any]:
    schema = _schema_name(schema_name, seed=schema_seed)
    conn = psycopg.connect(_database_url(database_url), row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
    conn.commit()
    return conn


def init_schema(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()

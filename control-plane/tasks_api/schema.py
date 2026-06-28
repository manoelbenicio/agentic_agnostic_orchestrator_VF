"""Postgres connection and schema helpers for the OTTL task trail."""

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
CREATE TABLE IF NOT EXISTS ottl_tasks (
    task_id             TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    priority            TEXT NOT NULL DEFAULT 'P2',
    agent               TEXT NOT NULL,
    pane                TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',
    eta_min             INTEGER NOT NULL DEFAULT 0,
    progress            INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    herdmaster_task_id  TEXT,
    herdmaster_state    TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ottl_tasks_status
    ON ottl_tasks(status);

CREATE INDEX IF NOT EXISTS idx_ottl_tasks_agent
    ON ottl_tasks(agent);

CREATE INDEX IF NOT EXISTS idx_ottl_tasks_priority
    ON ottl_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_ottl_tasks_status_created
    ON ottl_tasks(status, created_at DESC, task_id ASC);
CREATE INDEX IF NOT EXISTS idx_ottl_tasks_agent_status_created
    ON ottl_tasks(agent, status, created_at DESC, task_id ASC);
CREATE INDEX IF NOT EXISTS idx_ottl_tasks_priority_status_created
    ON ottl_tasks(priority, status, created_at DESC, task_id ASC);
"""


def _database_url(database_url: str | None = None) -> str:
    return database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _schema_name(name: str | None = None, *, seed: str | Path | None = None) -> str:
    if name:
        return name
    env_schema = os.environ.get("AOP_TASKS_SCHEMA")
    if env_schema:
        return env_schema
    return "hm_main"


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

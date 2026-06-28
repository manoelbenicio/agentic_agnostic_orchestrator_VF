"""Postgres schema for provisioning records and step results."""

from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from psycopg import sql

DEFAULT_SCHEMA = "aop_provisioning"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS provisioning_records (
    record_id    TEXT PRIMARY KEY,
    target       TEXT NOT NULL,
    status       TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS step_results (
    step_id          TEXT PRIMARY KEY,
    record_id        TEXT NOT NULL REFERENCES provisioning_records(record_id) ON DELETE CASCADE,
    step_name        TEXT NOT NULL,
    status           TEXT NOT NULL,
    output           TEXT,
    error            TEXT,
    duration_seconds DOUBLE PRECISION,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS provisioning_records_target_idx ON provisioning_records (target);
CREATE INDEX IF NOT EXISTS step_results_record_id_idx ON step_results (record_id);
"""


def init_schema(conn: psycopg.Connection[Any], *, schema_name: str | None = None) -> None:
    name = _schema_name(schema_name)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(name)))
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(name)))
        cur.execute(SCHEMA_SQL)
    conn.commit()


def _schema_name(name: str | None = None) -> str:
    candidate = name or os.environ.get("AOP_PROVISIONING_SCHEMA") or DEFAULT_SCHEMA
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate

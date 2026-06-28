"""Postgres schema for multi-tenant resource isolation."""

from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from psycopg import sql

DEFAULT_SCHEMA = "aop_tenants"

SCHEMA_SQL = """
-- Tenant namespaces: one row per isolated tenant workspace
CREATE TABLE IF NOT EXISTS tenant_namespaces (
    namespace_id    TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    tier            TEXT NOT NULL DEFAULT 'standard',
    labels          JSONB NOT NULL DEFAULT '{}'::jsonb,
    annotations     JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS tenant_namespaces_tenant_id_idx
    ON tenant_namespaces (tenant_id);

-- Resource quotas: per-dimension hard limits for each namespace
CREATE TABLE IF NOT EXISTS tenant_resource_quotas (
    id              SERIAL PRIMARY KEY,
    namespace_id    TEXT NOT NULL REFERENCES tenant_namespaces(namespace_id) ON DELETE CASCADE,
    dimension       TEXT NOT NULL,
    "limit"         BIGINT NOT NULL,
    request         BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace_id, dimension)
);

-- Resource usage tracking: current observed consumption per dimension
CREATE TABLE IF NOT EXISTS tenant_resource_usage (
    id              SERIAL PRIMARY KEY,
    namespace_id    TEXT NOT NULL REFERENCES tenant_namespaces(namespace_id) ON DELETE CASCADE,
    dimension       TEXT NOT NULL,
    used            BIGINT NOT NULL DEFAULT 0,
    reserved        BIGINT NOT NULL DEFAULT 0,
    measured_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace_id, dimension)
);

-- Quota enforcement audit log
CREATE TABLE IF NOT EXISTS tenant_quota_audit_log (
    audit_id        TEXT PRIMARY KEY,
    namespace_id    TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    action          TEXT NOT NULL,
    admitted        BOOLEAN NOT NULL,
    dimension       TEXT,
    requested       BIGINT,
    available       BIGINT,
    violations      JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS tenant_quota_audit_log_ns_idx
    ON tenant_quota_audit_log (namespace_id);
CREATE INDEX IF NOT EXISTS tenant_quota_audit_log_tenant_idx
    ON tenant_quota_audit_log (tenant_id);
"""


def init_schema(
    conn: psycopg.Connection[Any],
    *,
    schema_name: str | None = None,
) -> None:
    """Create the tenant isolation schema and tables."""
    name = _schema_name(schema_name)
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(name))
        )
        cur.execute(
            sql.SQL("SET search_path TO {}, public").format(sql.Identifier(name))
        )
        cur.execute(SCHEMA_SQL)
    conn.commit()


def _schema_name(name: str | None = None) -> str:
    candidate = name or os.environ.get("AOP_TENANTS_SCHEMA") or DEFAULT_SCHEMA
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate

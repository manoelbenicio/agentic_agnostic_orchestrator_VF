"""Postgres-backed topology repository."""

from __future__ import annotations

import dataclasses
import os
import re
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


DEFAULT_SCHEMA = "aop_topology"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS topology_snapshots (
    squad_id   TEXT PRIMARY KEY,
    nodes      JSONB NOT NULL,
    edges      JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class TopologyRepository:
    def __init__(self, connection_string: str, *, schema_name: str | None = None):
        self.conn_str = connection_string
        self.schema_name = _schema_name(schema_name)
        self._init_schema()

    def save_topology(self, squad_id: str, nodes: list, edges: list):
        payload = {
            "nodes": [_to_json_object(node) for node in nodes],
            "edges": [_to_json_object(edge) for edge in edges],
        }
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO topology_snapshots (squad_id, nodes, edges)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (squad_id) DO UPDATE SET
                        nodes = EXCLUDED.nodes,
                        edges = EXCLUDED.edges,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (squad_id, Jsonb(payload["nodes"]), Jsonb(payload["edges"])),
                )

    def get_topology(self, squad_id: str):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT nodes, edges
                    FROM topology_snapshots
                    WHERE squad_id = %s
                    """,
                    (squad_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"nodes": row["nodes"], "edges": row["edges"]}

    def _init_schema(self) -> None:
        with psycopg.connect(self.conn_str, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema_name)))
                cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema_name)))
                cur.execute(SCHEMA_SQL)

    def _connect(self) -> psycopg.Connection[Any]:
        conn = psycopg.connect(self.conn_str, row_factory=dict_row)
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema_name)))
        return conn


def _schema_name(name: str | None = None) -> str:
    candidate = name or os.environ.get("AOP_TOPOLOGY_SCHEMA") or DEFAULT_SCHEMA
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"invalid Postgres schema name: {candidate!r}")
    return candidate


def _to_json_object(value: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"topology item is not serializable: {type(value).__name__}")

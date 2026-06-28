"""Postgres repository for the dynamic agent registry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .models import AgentRecord, AgentStatus, PaneRef


class AgentRegistryRepository:
    """CRUD and pane mapping persistence for stable agent identities."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def create_agent(
        self,
        *,
        tenant_id: str,
        label: str,
        vendor: str,
        role: str,
        pane: PaneRef | None = None,
        stable_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> AgentRecord:
        """Create one stable internal identity and optional current pane mapping."""
        agent_id = agent_id or f"agent-{uuid4()}"
        stable_key = stable_key or agent_id
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO registry_agents (
                    agent_id, tenant_id, label, vendor, role, status,
                    workspace_id, pane_id, stable_key, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    agent_id,
                    tenant_id,
                    label,
                    vendor,
                    role,
                    AgentStatus.ACTIVE.value,
                    pane.workspace_id if pane else None,
                    pane.pane_id if pane else None,
                    stable_key,
                    Jsonb(metadata or {}),
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("registry agent insert returned no row")
            if pane is not None:
                self._insert_mapping(cur, agent_id, pane)
        self.conn.commit()
        return self._record(row)

    def get(self, agent_id: str) -> AgentRecord | None:
        """Return an agent by stable internal ID."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM registry_agents WHERE agent_id = %s", (agent_id,))
            row = cur.fetchone()
        return self._record(row) if row else None

    def find_by_stable_key(self, tenant_id: str, stable_key: str) -> AgentRecord | None:
        """Return an agent by tenant-scoped stable key."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM registry_agents WHERE tenant_id = %s AND stable_key = %s",
                (tenant_id, stable_key),
            )
            row = cur.fetchone()
        return self._record(row) if row else None

    def find_by_pane(self, pane: PaneRef) -> AgentRecord | None:
        """Return the active agent currently mapped to a Herdr pane."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM registry_agents
                WHERE workspace_id = %s AND pane_id = %s AND status = %s
                """,
                (pane.workspace_id, pane.pane_id, AgentStatus.ACTIVE.value),
            )
            row = cur.fetchone()
        return self._record(row) if row else None

    def list_agents(
        self,
        *,
        tenant_id: str | None = None,
        status: AgentStatus | None = None,
    ) -> list[AgentRecord]:
        """List source-of-truth identities, optionally filtered."""
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM registry_agents {where} ORDER BY created_at ASC, agent_id ASC",
                params,
            )
            rows = cur.fetchall()
        return [self._record(row) for row in rows]

    def update_agent(
        self,
        agent_id: str,
        *,
        label: str | None = None,
        vendor: str | None = None,
        role: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRecord | None:
        """Update mutable identity metadata without changing stable identity."""
        current = self.get(agent_id)
        if current is None:
            return None
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE registry_agents
                SET label = COALESCE(%s, label),
                    vendor = COALESCE(%s, vendor),
                    role = COALESCE(%s, role),
                    metadata = COALESCE(%s, metadata),
                    updated_at = CURRENT_TIMESTAMP
                WHERE agent_id = %s
                RETURNING *
                """,
                (
                    label,
                    vendor,
                    role,
                    Jsonb(metadata) if metadata is not None else None,
                    agent_id,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def remap_pane(self, agent_id: str, pane: PaneRef) -> AgentRecord | None:
        """Move a stable identity to a new current pane and retain mapping history."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE registry_pane_mappings
                SET retired_at = CURRENT_TIMESTAMP
                WHERE agent_id = %s AND retired_at IS NULL
                """,
                (agent_id,),
            )
            self._insert_mapping(cur, agent_id, pane)
            cur.execute(
                """
                UPDATE registry_agents
                SET workspace_id = %s,
                    pane_id = %s,
                    status = %s,
                    updated_at = CURRENT_TIMESTAMP,
                    removed_at = NULL
                WHERE agent_id = %s
                RETURNING *
                """,
                (pane.workspace_id, pane.pane_id, AgentStatus.ACTIVE.value, agent_id),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def remove_agent(self, agent_id: str) -> AgentRecord | None:
        """Deregister an agent in one database action without deleting history."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE registry_pane_mappings
                SET retired_at = CURRENT_TIMESTAMP
                WHERE agent_id = %s AND retired_at IS NULL
                """,
                (agent_id,),
            )
            cur.execute(
                """
                UPDATE registry_agents
                SET status = %s,
                    workspace_id = NULL,
                    pane_id = NULL,
                    updated_at = CURRENT_TIMESTAMP,
                    removed_at = CURRENT_TIMESTAMP
                WHERE agent_id = %s
                RETURNING *
                """,
                (AgentStatus.REMOVED.value, agent_id),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def mapping_history(self, agent_id: str) -> list[dict[str, Any]]:
        """Return pane mapping history for one stable identity."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT workspace_id, pane_id, session_id, metadata, observed_at, retired_at
                FROM registry_pane_mappings
                WHERE agent_id = %s
                ORDER BY observed_at ASC, id ASC
                """,
                (agent_id,),
            )
            return list(cur.fetchall())

    def count_agents(self) -> int:
        """Return total agent rows in this registry schema."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM registry_agents")
            row = cur.fetchone()
        return int(row["count"] if row else 0)

    def _insert_mapping(self, cur: psycopg.Cursor[Any], agent_id: str, pane: PaneRef) -> None:
        cur.execute(
            """
            INSERT INTO registry_pane_mappings (
                agent_id, workspace_id, pane_id, session_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (agent_id, pane.workspace_id, pane.pane_id, pane.session_id, Jsonb(pane.metadata)),
        )

    def _record(self, row: dict[str, Any]) -> AgentRecord:
        return AgentRecord(
            agent_id=str(row["agent_id"]),
            tenant_id=str(row["tenant_id"]),
            label=str(row["label"]),
            vendor=str(row["vendor"]),
            role=str(row["role"]),
            status=AgentStatus(str(row["status"])),
            workspace_id=row.get("workspace_id"),
            pane_id=row.get("pane_id"),
            stable_key=row.get("stable_key"),
            metadata=dict(row.get("metadata") or {}),
            created_at=self._dt(row.get("created_at")),
            updated_at=self._dt(row.get("updated_at")),
        )

    @staticmethod
    def _dt(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return None

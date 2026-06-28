"""Postgres repository for trace events and session artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .models import SessionArtifact, TraceEvent, TraceLayer, TraceSignalType


class TraceRepository:
    """Persistence and query operations for trace timelines."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def insert_event(self, event: TraceEvent) -> TraceEvent:
        """Persist one trace event."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trace_events (
                    event_id, trace_id, layer, signal_type, tenant_id, project_id,
                    issue_id, agent_id, runtime_id, message, token_burn,
                    seat_seconds, details, occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    event.event_id,
                    event.trace_id,
                    event.layer.value,
                    event.signal_type.value,
                    event.tenant_id,
                    event.project_id,
                    event.issue_id,
                    event.agent_id,
                    event.runtime_id,
                    event.message,
                    event.token_burn,
                    event.seat_seconds,
                    Jsonb(event.details),
                    event.occurred_at,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("trace insert returned no row")
        return self._event(row)

    def add_session_artifact(self, artifact: SessionArtifact) -> SessionArtifact:
        """Persist a queryable reference to a session recording artifact."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trace_session_artifacts (
                    trace_id, artifact_uri, runtime_id, agent_id, content_type,
                    metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trace_id, artifact_uri) DO UPDATE SET
                    runtime_id = EXCLUDED.runtime_id,
                    agent_id = EXCLUDED.agent_id,
                    content_type = EXCLUDED.content_type,
                    metadata = EXCLUDED.metadata
                RETURNING *
                """,
                (
                    artifact.trace_id,
                    artifact.artifact_uri,
                    artifact.runtime_id,
                    artifact.agent_id,
                    artifact.content_type,
                    Jsonb(artifact.metadata),
                    artifact.created_at,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("artifact insert returned no row")
        return self._artifact(row)

    def by_trace(self, trace_id: str) -> list[TraceEvent]:
        return self._query("trace_id = %s", (trace_id,))

    def by_agent(self, agent_id: str) -> list[TraceEvent]:
        return self._query("agent_id = %s", (agent_id,))

    def by_runtime(self, runtime_id: str) -> list[TraceEvent]:
        return self._query("runtime_id = %s", (runtime_id,))

    def artifacts_for_trace(self, trace_id: str) -> list[SessionArtifact]:
        """Return session artifacts linked to a trace."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM trace_session_artifacts
                WHERE trace_id = %s
                ORDER BY created_at ASC, artifact_uri ASC
                """,
                (trace_id,),
            )
            rows = cur.fetchall()
        return [self._artifact(row) for row in rows]

    def burn_by_agent_runtime(self) -> list[dict[str, Any]]:
        """Aggregate burn independently by agent and runtime."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT agent_id, runtime_id,
                    SUM(token_burn) AS token_burn,
                    SUM(seat_seconds) AS seat_seconds,
                    COUNT(*) AS event_count
                FROM trace_events
                GROUP BY agent_id, runtime_id
                ORDER BY agent_id ASC, runtime_id ASC
                """
            )
            return list(cur.fetchall())

    def _query(self, where: str, params: tuple[Any, ...]) -> list[TraceEvent]:
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM trace_events WHERE {where} ORDER BY occurred_at ASC, event_id ASC",  # nosec B608
                params,
            )
            rows = cur.fetchall()
        return [self._event(row) for row in rows]

    def _event(self, row: dict[str, Any]) -> TraceEvent:
        return TraceEvent(
            event_id=str(row["event_id"]),
            trace_id=str(row["trace_id"]),
            layer=TraceLayer(str(row["layer"])),
            signal_type=TraceSignalType(str(row["signal_type"])),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            issue_id=str(row["issue_id"]),
            agent_id=str(row["agent_id"]),
            runtime_id=str(row["runtime_id"]),
            message=str(row["message"]),
            token_burn=int(row["token_burn"] or 0),
            seat_seconds=int(row["seat_seconds"] or 0),
            details=dict(row.get("details") or {}),
            occurred_at=self._dt(row["occurred_at"]),
        )

    def _artifact(self, row: dict[str, Any]) -> SessionArtifact:
        return SessionArtifact(
            trace_id=str(row["trace_id"]),
            artifact_uri=str(row["artifact_uri"]),
            runtime_id=str(row["runtime_id"]),
            agent_id=str(row["agent_id"]),
            content_type=str(row["content_type"]),
            metadata=dict(row.get("metadata") or {}),
            created_at=self._dt(row["created_at"]),
        )

    @staticmethod
    def _dt(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        raise TypeError(f"expected datetime, got {type(value).__name__}")

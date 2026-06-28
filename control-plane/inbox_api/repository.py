"""Postgres-backed repository for inbox events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg

from .models import InboxEventRecord, InboxEventType


class InboxRepository:
    """Persist and retrieve inbox events from Postgres."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def create(
        self,
        *,
        tenant_id: str,
        type: InboxEventType = InboxEventType.INFO,
        title: str,
        message: str = "",
        event_id: str | None = None,
    ) -> InboxEventRecord:
        event_id = event_id or f"inbox-{uuid4()}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO inbox_events (id, tenant_id, type, title, message)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (event_id, tenant_id, type.value, title, message),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("inbox event insert returned no row")
        return self._record(row)

    def list(
        self,
        *,
        tenant_id: str | None = None,
        read: bool | None = None,
        archived: bool = False,
    ) -> list[InboxEventRecord]:
        clauses = ["archived = %s"]
        params: list[Any] = [archived]
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if read is not None:
            clauses.append("read = %s")
            params.append(read)
        where = "WHERE " + " AND ".join(clauses)
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM inbox_events {where} ORDER BY created_at DESC, id ASC",
                params,
            )
            rows = cur.fetchall()
        return [self._record(row) for row in rows]

    def get(self, event_id: str) -> InboxEventRecord | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM inbox_events WHERE id = %s", (event_id,))
            row = cur.fetchone()
        return self._record(row) if row else None

    def mark_read(self, event_id: str) -> InboxEventRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inbox_events
                SET read = TRUE
                WHERE id = %s AND archived = FALSE
                RETURNING *
                """,
                (event_id,),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def bulk_archive(self, event_ids: list[str]) -> int:
        if not event_ids:
            return 0
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE inbox_events
                SET archived = TRUE
                WHERE id = ANY(%s) AND archived = FALSE
                """,
                (event_ids,),
            )
            count = cur.rowcount
        self.conn.commit()
        return count

    def unread_count(self, *, tenant_id: str | None = None) -> int:
        clauses = ["read = FALSE", "archived = FALSE"]
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        where = "WHERE " + " AND ".join(clauses)
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS count FROM inbox_events {where}", params)
            row = cur.fetchone()
        return int(row["count"] if row else 0)

    def _record(self, row: dict[str, Any]) -> InboxEventRecord:
        return InboxEventRecord(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            type=InboxEventType(str(row["type"])),
            title=str(row["title"]),
            message=str(row.get("message") or ""),
            read=bool(row.get("read", False)),
            archived=bool(row.get("archived", False)),
            created_at=self._dt(row.get("created_at")),
        )

    def _dt(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        raise TypeError(f"expected datetime, got {type(value)!r}")

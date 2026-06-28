"""Repository for vendor login sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    seat_id: str
    tenant_id: str
    vendor: str
    status: str
    status_reason: str | None = None
    verification_uri: str | None = None
    user_code: str | None = None
    device_code_ref: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionsRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def create(self, record: SessionRecord) -> SessionRecord:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (
                    session_id, seat_id, tenant_id, vendor, status, status_reason,
                    verification_uri, user_code, device_code_ref, expires_at, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING session_id, seat_id, tenant_id, vendor, status, status_reason,
                    verification_uri, user_code, device_code_ref, expires_at, metadata
                """,
                (
                    record.session_id,
                    record.seat_id,
                    record.tenant_id,
                    record.vendor,
                    record.status,
                    record.status_reason,
                    record.verification_uri,
                    record.user_code,
                    record.device_code_ref,
                    record.expires_at,
                    Jsonb(record.metadata),
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        return _record(row)

    def get(self, session_id: str) -> SessionRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, seat_id, tenant_id, vendor, status, status_reason,
                    verification_uri, user_code, device_code_ref, expires_at, metadata
                FROM sessions
                WHERE session_id = %s
                """,
                (session_id,),
            )
            row = cur.fetchone()
        return _record(row) if row else None

    def list(
        self,
        *,
        seat_id: str | None = None,
        tenant_id: str | None = None,
        vendor: str | None = None,
    ) -> list[SessionRecord]:
        params: list[Any] = []
        clauses: list[str] = []
        if seat_id:
            clauses.append("seat_id = %s")
            params.append(seat_id)
        if tenant_id:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if vendor:
            clauses.append("vendor = %s")
            params.append(vendor)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT session_id, seat_id, tenant_id, vendor, status, status_reason,
                    verification_uri, user_code, device_code_ref, expires_at, metadata
                FROM sessions
                {where}
                ORDER BY created_at DESC, session_id
                """,
                params,
            )
            return [_record(row) for row in cur.fetchall()]

    def active_counts_by_seat(self) -> dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT seat_id, COUNT(*) AS active_count
                FROM sessions
                WHERE status IN ('pending', 'authenticated')
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                GROUP BY seat_id
                """
            )
            return {str(row["seat_id"]): int(row["active_count"]) for row in cur.fetchall()}

    def set_status(self, session_id: str, status: str, status_reason: str | None) -> SessionRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sessions
                SET status = %s, status_reason = %s, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                RETURNING session_id, seat_id, tenant_id, vendor, status, status_reason,
                    verification_uri, user_code, device_code_ref, expires_at, metadata
                """,
                (status, status_reason, session_id),
            )
            row = cur.fetchone()
        self.conn.commit()
        return _record(row) if row else None


def _record(row: dict[str, Any]) -> SessionRecord:
    return SessionRecord(
        session_id=row["session_id"],
        seat_id=row["seat_id"],
        tenant_id=row["tenant_id"],
        vendor=row["vendor"],
        status=row["status"],
        status_reason=row.get("status_reason"),
        verification_uri=row.get("verification_uri"),
        user_code=row.get("user_code"),
        device_code_ref=row.get("device_code_ref"),
        expires_at=row.get("expires_at"),
        metadata=dict(row.get("metadata") or {}),
    )

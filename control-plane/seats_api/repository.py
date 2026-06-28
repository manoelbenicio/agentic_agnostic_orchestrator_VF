"""Repository for persistent control-plane seats."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


@dataclass(frozen=True, slots=True)
class SeatRecord:
    seat_id: str
    tenant_id: str
    vendor: str
    home_dir: str
    config_dir: str
    display_name: str | None = None
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class SeatsRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def list(self, *, tenant_id: str | None = None, vendor: str | None = None) -> list[SeatRecord]:
        clauses: list[str] = []
        params: list[Any] = []
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
                SELECT seat_id, tenant_id, vendor, home_dir, config_dir, display_name, active, metadata
                FROM seats
                {where}
                ORDER BY tenant_id, vendor, seat_id
                """,
                params,
            )
            return [_record(row) for row in cur.fetchall()]

    def get(self, seat_id: str) -> SeatRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT seat_id, tenant_id, vendor, home_dir, config_dir, display_name, active, metadata
                FROM seats
                WHERE seat_id = %s
                """,
                (seat_id,),
            )
            row = cur.fetchone()
        return _record(row) if row else None

    def upsert(self, record: SeatRecord) -> SeatRecord:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO seats (seat_id, tenant_id, vendor, home_dir, config_dir, display_name, active, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (seat_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    vendor = EXCLUDED.vendor,
                    home_dir = EXCLUDED.home_dir,
                    config_dir = EXCLUDED.config_dir,
                    display_name = EXCLUDED.display_name,
                    active = EXCLUDED.active,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING seat_id, tenant_id, vendor, home_dir, config_dir, display_name, active, metadata
                """,
                (
                    record.seat_id,
                    record.tenant_id,
                    record.vendor,
                    record.home_dir,
                    record.config_dir,
                    record.display_name,
                    record.active,
                    Jsonb(record.metadata),
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        return _record(row)

    def update(self, seat_id: str, changes: dict[str, Any]) -> SeatRecord | None:
        current = self.get(seat_id)
        if current is None:
            return None
        merged = SeatRecord(
            seat_id=seat_id,
            tenant_id=changes.get("tenant_id", current.tenant_id),
            vendor=changes.get("vendor", current.vendor),
            home_dir=changes.get("home_dir", current.home_dir),
            config_dir=changes.get("config_dir", current.config_dir),
            display_name=changes.get("display_name", current.display_name),
            active=changes.get("active", current.active),
            metadata=changes.get("metadata", current.metadata),
        )
        return self.upsert(merged)

    def remove(self, seat_id: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM seats WHERE seat_id = %s", (seat_id,))
            removed = cur.rowcount > 0
        self.conn.commit()
        return removed


def _record(row: dict[str, Any]) -> SeatRecord:
    return SeatRecord(
        seat_id=row["seat_id"],
        tenant_id=row["tenant_id"],
        vendor=row["vendor"],
        home_dir=row["home_dir"],
        config_dir=row["config_dir"],
        display_name=row.get("display_name"),
        active=bool(row["active"]),
        metadata=dict(row.get("metadata") or {}),
    )

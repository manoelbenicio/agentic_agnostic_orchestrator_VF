"""Postgres repository for FinOps records."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .models import (
    Attribution,
    BillingMode,
    CostEngine,
    CostRecord,
    DimensionRollup,
    ProjectRollup,
    RightSizingRecommendation,
)


class FinOpsRepository:
    """Persistence operations for cost records and seat utilization."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def insert_cost(self, record: CostRecord) -> CostRecord:
        """Persist one token or seat utilization cost record."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finops_cost_records (
                    cost_id, engine, billing_mode, tenant_id, project_id, issue_id,
                    agent_id, runtime_id, trace_id, cost_usd, usage_units, metadata,
                    occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    record.cost_id,
                    record.engine.value,
                    record.billing_mode.value,
                    record.attribution.tenant_id,
                    record.attribution.project_id,
                    record.attribution.issue_id,
                    record.attribution.agent_id,
                    record.attribution.runtime_id,
                    record.trace_id,
                    record.cost_usd,
                    Jsonb({key: str(value) for key, value in record.usage_units.items()}),
                    Jsonb(record.metadata),
                    record.occurred_at,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("cost insert returned no row")
        return self._record(row)

    def insert_seat_observation(
        self,
        *,
        tenant_id: str,
        seat_id: str,
        vendor: str,
        used_seconds: int,
        period_seconds: int,
        period_cost_usd: Decimal,
    ) -> None:
        """Persist utilization observed for a paid subscription seat."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finops_seat_usage (
                    tenant_id, seat_id, vendor, used_seconds, period_seconds, period_cost_usd
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, seat_id, vendor, used_seconds, period_seconds, period_cost_usd),
            )
        self.conn.commit()

    def costs_for_project(self, tenant_id: str, project_id: str) -> list[CostRecord]:
        """Return all cost records for a tenant/project pair."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM finops_cost_records
                WHERE tenant_id = %s AND project_id = %s
                ORDER BY occurred_at ASC, cost_id ASC
                """,
                (tenant_id, project_id),
            )
            rows = cur.fetchall()
        return [self._record(row) for row in rows]

    def rollup_project(self, tenant_id: str, project_id: str) -> ProjectRollup:
        """Aggregate costs at project level."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total,
                    COALESCE(SUM(CASE WHEN engine = 'token' THEN cost_usd ELSE 0 END), 0) AS token_total,
                    COALESCE(SUM(CASE WHEN engine = 'seat' THEN cost_usd ELSE 0 END), 0) AS seat_total,
                    COUNT(*) AS count
                FROM finops_cost_records
                WHERE tenant_id = %s AND project_id = %s
                """,
                (tenant_id, project_id),
            )
            row = cur.fetchone() or {}
        return ProjectRollup(
            tenant_id=tenant_id,
            project_id=project_id,
            total_cost_usd=Decimal(str(row.get("total", "0"))),
            token_cost_usd=Decimal(str(row.get("token_total", "0"))),
            seat_cost_usd=Decimal(str(row.get("seat_total", "0"))),
            record_count=int(row.get("count") or 0),
        )

    # Allowed grouping dimensions mapped to their SQL source. ``model`` reads from
    # the JSONB metadata; the others are first-class columns. Keys are validated
    # against this map to prevent SQL injection via the dimension name.
    _DIMENSIONS: dict[str, str] = {
        "model": "metadata->>'model'",
        "vendor": "metadata->>'vendor'",
        "issue_id": "issue_id",
        "agent_id": "agent_id",
        "runtime_id": "runtime_id",
    }

    def rollup_by_dimension(
        self,
        tenant_id: str,
        project_id: str,
        dimension: str,
    ) -> list[DimensionRollup]:
        """Aggregate project cost grouped by a single attribution dimension.

        Supported dimensions: ``model``, ``issue_id``, ``agent_id``,
        ``runtime_id``. ``model`` is read from the ``metadata->>'model'`` JSONB
        field. Buckets are ordered by descending total cost.
        """
        expr = self._DIMENSIONS.get(dimension)
        if expr is None:
            raise ValueError(
                f"unsupported rollup dimension {dimension!r}; allowed: {sorted(self._DIMENSIONS)}"
            )
        # ``expr`` comes only from the trusted _DIMENSIONS map, never user input.
        query = f"""
            SELECT
                COALESCE({expr}, 'unknown') AS key,
                COALESCE(SUM(cost_usd), 0) AS total,
                COALESCE(SUM(CASE WHEN engine = 'token' THEN cost_usd ELSE 0 END), 0) AS token_total,
                COALESCE(SUM(CASE WHEN engine = 'seat' THEN cost_usd ELSE 0 END), 0) AS seat_total,
                COUNT(*) AS count
            FROM finops_cost_records
            WHERE tenant_id = %s AND project_id = %s
            GROUP BY COALESCE({expr}, 'unknown')
            ORDER BY total DESC, key ASC
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (tenant_id, project_id))
            rows = cur.fetchall()
        return [
            DimensionRollup(
                tenant_id=tenant_id,
                project_id=project_id,
                dimension=dimension,
                key=str(row["key"]),
                total_cost_usd=Decimal(str(row["total"])),
                token_cost_usd=Decimal(str(row["token_total"])),
                seat_cost_usd=Decimal(str(row["seat_total"])),
                record_count=int(row["count"] or 0),
            )
            for row in rows
        ]

    def list_projects(self) -> list[tuple[str, str]]:
        """Return all distinct (tenant_id, project_id) pairs with cost records.

        Used by the dynamic Prometheus exporter so /metrics reflects every real
        tenant/project instead of a single hard-coded pair.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT tenant_id, project_id
                FROM finops_cost_records
                ORDER BY tenant_id ASC, project_id ASC
                """
            )
            rows = cur.fetchall()
        return [(str(row["tenant_id"]), str(row["project_id"])) for row in rows]

    def idle_seat_recommendations(
        self,
        *,
        tenant_id: str,
        idle_threshold_pct: Decimal = Decimal("10"),
    ) -> list[RightSizingRecommendation]:
        """Return right-sizing guidance for seats below a utilization threshold."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    tenant_id,
                    seat_id,
                    vendor,
                    SUM(used_seconds) AS used_seconds,
                    SUM(period_seconds) AS period_seconds
                FROM finops_seat_usage
                WHERE tenant_id = %s
                GROUP BY tenant_id, seat_id, vendor
                ORDER BY seat_id ASC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        recommendations: list[RightSizingRecommendation] = []
        for row in rows:
            used = Decimal(str(row["used_seconds"] or 0))
            period = Decimal(str(row["period_seconds"] or 0))
            utilization = Decimal("0") if period == 0 else (used / period) * Decimal("100")
            idle = utilization < idle_threshold_pct
            recommendations.append(
                RightSizingRecommendation(
                    seat_id=str(row["seat_id"]),
                    tenant_id=str(row["tenant_id"]),
                    vendor=str(row["vendor"]),
                    utilization_pct=utilization.quantize(Decimal("0.01")),
                    idle=idle,
                    recommendation="release_or_downsize" if idle else "keep",
                )
            )
        return recommendations

    def _record(self, row: dict[str, Any]) -> CostRecord:
        return CostRecord(
            cost_id=str(row["cost_id"]),
            engine=CostEngine(str(row["engine"])),
            billing_mode=BillingMode(str(row["billing_mode"])),
            attribution=Attribution(
                tenant_id=str(row["tenant_id"]),
                project_id=str(row["project_id"]),
                issue_id=str(row["issue_id"]),
                agent_id=str(row["agent_id"]),
                runtime_id=str(row["runtime_id"]),
            ),
            cost_usd=Decimal(str(row["cost_usd"])),
            usage_units={
                key: Decimal(str(value))
                for key, value in dict(row.get("usage_units") or {}).items()
            },
            occurred_at=self._dt(row["occurred_at"]),
            trace_id=row.get("trace_id"),
            metadata=dict(row.get("metadata") or {}),
        )

    @staticmethod
    def _dt(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        raise TypeError(f"expected datetime, got {type(value).__name__}")

"""Postgres-backed CRUD repository for projects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .models import ProjectRecord, ProjectStatus


class ProjectRepository:
    """Persist and retrieve projects from Postgres."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def create(
        self,
        *,
        tenant_id: str,
        name: str,
        description: str | None = None,
        status: ProjectStatus = ProjectStatus.ACTIVE,
        metadata: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> ProjectRecord:
        project_id = project_id or f"project-{uuid4()}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (
                    project_id, tenant_id, name, description, status, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    project_id,
                    tenant_id,
                    name,
                    description,
                    status.value,
                    Jsonb(metadata or {}),
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("project insert returned no row")
        return self._record(row)

    def list(self, *, tenant_id: str | None = None) -> list[ProjectRecord]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        where = "WHERE " + " AND ".join(clauses)
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM projects {where} ORDER BY created_at DESC, project_id ASC",
                params,
            )
            rows = cur.fetchall()
        return [self._record(row) for row in rows]

    def get(self, project_id: str) -> ProjectRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM projects WHERE project_id = %s AND deleted_at IS NULL",
                (project_id,),
            )
            row = cur.fetchone()
        return self._record(row) if row else None

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProjectRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE projects
                SET name = COALESCE(%s, name),
                    description = COALESCE(%s, description),
                    status = COALESCE(%s, status),
                    metadata = COALESCE(%s, metadata),
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = %s AND deleted_at IS NULL
                RETURNING *
                """,
                (
                    name,
                    description,
                    status.value if status is not None else None,
                    Jsonb(metadata) if metadata is not None else None,
                    project_id,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def delete(self, project_id: str) -> ProjectRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE projects
                SET deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE project_id = %s AND deleted_at IS NULL
                RETURNING *
                """,
                (project_id,),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM projects WHERE deleted_at IS NULL")
            row = cur.fetchone()
        return int(row["count"] if row else 0)

    def _record(self, row: dict[str, Any]) -> ProjectRecord:
        return ProjectRecord(
            project_id=str(row["project_id"]),
            tenant_id=str(row["tenant_id"]),
            name=str(row["name"]),
            description=row.get("description"),
            status=ProjectStatus(str(row["status"])),
            metadata=dict(row.get("metadata") or {}),
            created_at=self._dt(row.get("created_at")),
            updated_at=self._dt(row.get("updated_at")),
            deleted_at=self._dt(row.get("deleted_at")),
        )

    def _dt(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        raise TypeError(f"expected datetime, got {type(value)!r}")

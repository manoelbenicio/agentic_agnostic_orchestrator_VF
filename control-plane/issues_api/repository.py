"""Postgres-backed CRUD repository for issues."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .models import IssuePriority, IssueRecord, IssueStatus


class IssueRepository:
    """Persist and retrieve issue tracker records from Postgres."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def create(
        self,
        *,
        tenant_id: str,
        project_id: str,
        title: str,
        description: str | None = None,
        status: IssueStatus = IssueStatus.BACKLOG,
        priority: IssuePriority = IssuePriority.MEDIUM,
        assignee_runtime: str | None = None,
        operation_mode: str = "terminal",
        due_date: date | None = None,
        metadata: dict[str, Any] | None = None,
        issue_id: str | None = None,
    ) -> IssueRecord:
        issue_id = issue_id or f"issue-{uuid4()}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO issues (
                    issue_id, tenant_id, project_id, title, description, status, priority,
                    assignee_runtime, operation_mode, due_date, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    issue_id,
                    tenant_id,
                    project_id,
                    title,
                    description,
                    status.value,
                    priority.value,
                    assignee_runtime,
                    operation_mode,
                    due_date,
                    Jsonb(metadata or {}),
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("issue insert returned no row")
        return self._record(row)

    def list(
        self,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        status: IssueStatus | None = None,
        assignee_runtime: str | None = None,
    ) -> list[IssueRecord]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if project_id is not None:
            clauses.append("project_id = %s")
            params.append(project_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status.value)
        if assignee_runtime is not None:
            clauses.append("assignee_runtime = %s")
            params.append(assignee_runtime)
        where = "WHERE " + " AND ".join(clauses)
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM issues {where} ORDER BY created_at DESC, issue_id ASC",
                params,
            )
            rows = cur.fetchall()
        return [self._record(row) for row in rows]

    def list_my(
        self,
        *,
        agent_id: str,
        scope: str = "all",
        tenant_id: str | None = None,
        project_id: str | None = None,
        status: IssueStatus | None = None,
    ) -> list[IssueRecord]:
        """Return issues relevant to a specific agent/user.

        Scopes:
        - all: issues assigned to OR created by the agent
        - assigned: issues where assignee_runtime matches agent_id
        - created: issues where metadata ownership fields match agent_id
        - my-agents: issues where assignee_runtime starts with agent_id prefix
        """
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []

        if scope == "assigned":
            clauses.append("assignee_runtime = %s")
            params.append(agent_id)
        elif scope == "created":
            clauses.append(self._created_by_clause())
            params.extend([agent_id] * 4)
        elif scope == "my-agents":
            clauses.append("assignee_runtime LIKE %s ESCAPE '\\'")
            params.append(f"{self._like_escape(agent_id)}%")
        else:  # "all" — assigned to or created by
            clauses.append(f"(assignee_runtime = %s OR {self._created_by_clause()})")
            params.extend([agent_id, agent_id, agent_id, agent_id, agent_id])

        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if project_id is not None:
            clauses.append("project_id = %s")
            params.append(project_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status.value)

        where = "WHERE " + " AND ".join(clauses)
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM issues {where} ORDER BY created_at DESC, issue_id ASC",
                params,
            )
            rows = cur.fetchall()
        return [self._record(row) for row in rows]

    def _created_by_clause(self) -> str:
        return (
            "(metadata->>'created_by' = %s OR "
            "metadata->>'created_by_agent' = %s OR "
            "metadata->>'owner' = %s OR "
            "metadata->>'reporter' = %s)"
        )

    def _like_escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def get(self, issue_id: str) -> IssueRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM issues WHERE issue_id = %s AND deleted_at IS NULL",
                (issue_id,),
            )
            row = cur.fetchone()
        return self._record(row) if row else None

    def update(
        self,
        issue_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: IssueStatus | None = None,
        priority: IssuePriority | None = None,
        assignee_runtime: str | None = None,
        operation_mode: str | None = None,
        due_date: date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IssueRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE issues
                SET title = COALESCE(%s, title),
                    description = COALESCE(%s, description),
                    status = COALESCE(%s, status),
                    priority = COALESCE(%s, priority),
                    assignee_runtime = COALESCE(%s, assignee_runtime),
                    operation_mode = COALESCE(%s, operation_mode),
                    due_date = COALESCE(%s, due_date),
                    metadata = COALESCE(%s, metadata),
                    updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = %s AND deleted_at IS NULL
                RETURNING *
                """,
                (
                    title,
                    description,
                    status.value if status is not None else None,
                    priority.value if priority is not None else None,
                    assignee_runtime,
                    operation_mode,
                    due_date,
                    Jsonb(metadata) if metadata is not None else None,
                    issue_id,
                ),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def delete(self, issue_id: str) -> IssueRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE issues
                SET deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = %s AND deleted_at IS NULL
                RETURNING *
                """,
                (issue_id,),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._record(row) if row else None

    def _record(self, row: dict[str, Any]) -> IssueRecord:
        return IssueRecord(
            issue_id=str(row["issue_id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            title=str(row["title"]),
            description=row.get("description"),
            status=IssueStatus(str(row["status"])),
            priority=IssuePriority(str(row["priority"])),
            assignee_runtime=row.get("assignee_runtime"),
            operation_mode=str(row["operation_mode"]),
            due_date=self._date(row.get("due_date")),
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

    def _date(self, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        raise TypeError(f"expected date, got {type(value)!r}")

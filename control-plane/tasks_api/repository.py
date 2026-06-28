from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .models import TaskPriority, TaskRecord, TaskStatus
from .schema import _schema_name


class TaskRepository:
    """Repository for OTTL task records in Postgres."""

    def __init__(self, conn: psycopg.Connection[Any], *, schema_name: str | None = None) -> None:
        self._conn = conn
        self._schema = _schema_name(schema_name)

    def list(
        self,
        *,
        status: TaskStatus | None = None,
        agent: str | None = None,
        priority: TaskPriority | None = None,
    ) -> list[TaskRecord]:
        where: list[sql.Composable] = []
        params: dict[str, Any] = {}
        if status is not None:
            where.append(sql.SQL("status = %(status)s"))
            params["status"] = status.value
        if agent is not None:
            where.append(sql.SQL("agent = %(agent)s"))
            params["agent"] = agent
        if priority is not None:
            where.append(sql.SQL("priority = %(priority)s"))
            params["priority"] = priority.value

        query = sql.SQL(
            """
            SELECT task_id, title, priority, agent, pane, status, eta_min, progress,
                   herdmaster_task_id, herdmaster_state, metadata,
                   created_at, updated_at, last_seen_at
            FROM {}.ottl_tasks
            """
        ).format(sql.Identifier(self._schema))
        if where:
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where)
        query += sql.SQL(" ORDER BY created_at DESC")

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return [self._row_to_task(row) for row in cur.fetchall()]

    def list_tasks(self) -> list[TaskRecord]:
        return self.list()

    def get(self, task_id: str) -> TaskRecord | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                sql.SQL(
                    """
                    SELECT task_id, title, priority, agent, pane, status, eta_min, progress,
                           herdmaster_task_id, herdmaster_state, metadata,
                           created_at, updated_at, last_seen_at
                    FROM {}.ottl_tasks
                    WHERE task_id = %(task_id)s
                    """
                ).format(sql.Identifier(self._schema)),
                {"task_id": task_id},
            )
            row = cur.fetchone()
            return self._row_to_task(row) if row else None

    def upsert(
        self,
        *,
        task_id: str,
        title: str,
        priority: TaskPriority,
        agent: str,
        pane: str,
        status: TaskStatus,
        eta_min: int,
        progress: int,
        herdmaster_task_id: str | None = None,
        herdmaster_state: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord:
        self.upsert_task(
            TaskRecord(
                task_id=task_id,
                title=title,
                priority=priority,
                agent=agent,
                pane=pane,
                status=status,
                eta_min=eta_min,
                progress=progress,
                herdmaster_task_id=herdmaster_task_id,
                herdmaster_state=herdmaster_state,
                metadata=metadata or {},
            )
        )
        task = self.get(task_id)
        if task is None:
            raise RuntimeError(f"upserted task {task_id} was not found")
        return task

    def upsert_task(self, task: TaskRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                INSERT INTO {}.ottl_tasks (
                    task_id, title, priority, agent, pane, status, eta_min, progress,
                    herdmaster_task_id, herdmaster_state, metadata
                ) VALUES (
                    %(task_id)s, %(title)s, %(priority)s, %(agent)s, %(pane)s, %(status)s, %(eta_min)s, %(progress)s,
                    %(herdmaster_task_id)s, %(herdmaster_state)s, %(metadata)s
                )
                ON CONFLICT (task_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    priority = EXCLUDED.priority,
                    agent = EXCLUDED.agent,
                    pane = EXCLUDED.pane,
                    status = EXCLUDED.status,
                    eta_min = EXCLUDED.eta_min,
                    progress = EXCLUDED.progress,
                    herdmaster_task_id = EXCLUDED.herdmaster_task_id,
                    herdmaster_state = EXCLUDED.herdmaster_state,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP,
                    last_seen_at = CURRENT_TIMESTAMP
                """
                ).format(sql.Identifier(self._schema)),
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "priority": task.priority.value,
                    "agent": task.agent,
                    "pane": task.pane,
                    "status": task.status.value,
                    "eta_min": task.eta_min,
                    "progress": task.progress,
                    "herdmaster_task_id": task.herdmaster_task_id,
                    "herdmaster_state": task.herdmaster_state,
                    "metadata": json.dumps(task.metadata or {}),
                },
            )
        self._conn.commit()

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        eta_min: int | None = None,
        progress: int | None = None,
        herdmaster_task_id: str | None = None,
        herdmaster_state: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskRecord | None:
        current = self.get(task_id)
        if current is None:
            return None
        return self.upsert(
            task_id=current.task_id,
            title=current.title,
            priority=current.priority,
            agent=current.agent,
            pane=current.pane,
            status=status if status is not None else current.status,
            eta_min=eta_min if eta_min is not None else current.eta_min,
            progress=progress if progress is not None else current.progress,
            herdmaster_task_id=herdmaster_task_id if herdmaster_task_id is not None else current.herdmaster_task_id,
            herdmaster_state=herdmaster_state if herdmaster_state is not None else current.herdmaster_state,
            metadata=metadata if metadata is not None else current.metadata,
        )

    def board(self) -> dict[str, Any]:
        tasks = self.list()
        total = len(tasks)
        done = sum(1 for task in tasks if task.status is TaskStatus.DONE)
        total_progress = sum(task.progress for task in tasks)
        by_status: dict[str, dict[str, int]] = {
            status.value: {"count": 0, "eta_min": 0, "progress": 0}
            for status in TaskStatus
        }
        for task in tasks:
            bucket = by_status[task.status.value]
            bucket["count"] += 1
            bucket["eta_min"] += task.eta_min
            bucket["progress"] += task.progress
        return {
            "total_tasks": total,
            "done": done,
            "overall_progress": round(total_progress / total, 2) if total else 0.0,
            "total_eta_min": sum(task.eta_min for task in tasks if task.status is not TaskStatus.DONE),
            "by_status": by_status,
        }

    def list_herdmaster_tasks(self) -> list[dict[str, Any]]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                sql.SQL(
                    """
                SELECT id, title, state, assigned_to, priority, created_at, updated_at
                FROM {}.tasks
                ORDER BY created_at DESC
                """
                ).format(sql.Identifier(self._schema))
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "state": r["state"],
                    "assigned_to": r["assigned_to"],
                    "priority": r["priority"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                }
                for r in rows
            ]

    def _row_to_task(self, row: dict[str, Any]) -> TaskRecord:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return TaskRecord(
            task_id=row["task_id"],
            title=row["title"],
            priority=TaskPriority(row["priority"]),
            agent=row["agent"],
            pane=row["pane"],
            status=TaskStatus(row["status"]),
            eta_min=row["eta_min"],
            progress=row["progress"],
            herdmaster_task_id=row["herdmaster_task_id"],
            herdmaster_state=row["herdmaster_state"],
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_seen_at=row["last_seen_at"],
        )

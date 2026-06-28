"""Repository classes for HerdMaster's Postgres data layer.

All write methods follow the R1 robustness pattern: execute+commit are wrapped
in try/except, and conn.rollback() is called on any error before re-raising,
to prevent the connection from staying in an aborted transaction state.

DECISION: Rollback in error handler before reusing connection
SOURCE:   https://www.psycopg.org/psycopg3/docs/basic/transactions.html
REF:      \"Transaction contexts\" — rollback on exception exit
RATIONALE: psycopg3 connections default to autocommit=False. An error during
          SQL execution leaves the connection in InFailedTransaction state.
          Any subsequent SQL will fail with \"current transaction is aborted\"
          unless an explicit rollback is issued.
VERSION:  psycopg 3.3.x
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator, Mapping

logger = logging.getLogger(__name__)



def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    """Return a lexicographically time-ordered identifier using a UTC timestamp and UUID4."""
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    value = f"{stamp}-{uuid.uuid4().hex}"
    return f"{prefix}{value}" if prefix else value


def _json_dumps(value: object) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _json_loads(value: object) -> object:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return value
    return json.loads(value)


def _normalize_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return value


def _row_to_dict(row: Mapping[str, Any] | None, json_fields: set[str] | None = None) -> dict[str, object] | None:
    if row is None:
        return None
    data = {key: _normalize_value(value) for key, value in dict(row).items()}
    for field in json_fields or set():
        if field in data:
            data[field] = _json_loads(data[field])
    return data


def _rows_to_dicts(rows: list[Mapping[str, Any]], json_fields: set[str] | None = None) -> list[dict[str, object]]:
    return [_row_to_dict(row, json_fields) or {} for row in rows]


@contextmanager
def _transaction(conn: Any) -> Iterator[None]:
    """Run SQL in a transaction and rollback before connection reuse on error."""
    try:
        transaction = getattr(conn, "transaction", None)
        if callable(transaction):
            with transaction():
                yield
        else:
            yield
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            logger.warning("rollback after failed repository transaction also failed", exc_info=True)
        raise


class AgentRepo:
    """Persistence operations for the agents registry and agent metrics."""

    def __init__(self, conn: Any) -> None:
        """Create an agent repository bound to an existing database connection."""
        self.conn = conn

    def upsert(
        self,
        agent_id: str,
        label: str,
        agent_type: str,
        role: str,
        *,
        herdr_pane: str | None = None,
        herdr_ws: str | None = None,
        state: str = "unknown",
        health: str = "healthy",
        strengths: object | None = None,
    ) -> dict[str, object]:
        """Insert or update an agent and return the stored row."""
        with _transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO agents (id, label, type, role, herdr_pane, herdr_ws, state, health, strengths, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    label=excluded.label,
                    type=excluded.type,
                    role=excluded.role,
                    herdr_pane=excluded.herdr_pane,
                    herdr_ws=excluded.herdr_ws,
                    state=excluded.state,
                    health=excluded.health,
                    strengths=excluded.strengths,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (agent_id, label, agent_type, role, herdr_pane, herdr_ws, state, health, _json_dumps(strengths)),
            )
        agent = self.get(agent_id)
        if agent is None:
            raise RuntimeError(f"agent upsert failed for {agent_id}")
        return agent

    def get(self, agent_id: str) -> dict[str, object] | None:
        """Return one agent by ID, or None when it does not exist."""
        row = self.conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return _row_to_dict(row, {"strengths"})

    def list(self) -> list[dict[str, object]]:
        """Return all agents ordered by ID."""
        rows = self.conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
        return _rows_to_dicts(rows, {"strengths"})

    def update(self, agent_id: str, **fields: object) -> dict[str, object] | None:
        """Update editable agent fields and return the stored row, or None."""
        allowed = {
            "label",
            "type",
            "role",
            "herdr_pane",
            "herdr_ws",
            "state",
            "health",
            "strengths",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return self.get(agent_id)
        columns: list[str] = []
        params: list[object] = []
        for key, value in values.items():
            columns.append(f"{key} = ?")
            params.append(_json_dumps(value) if key == "strengths" else value)
        params.append(agent_id)
        with _transaction(self.conn):
            cur = self.conn.execute(
                f"""
                UPDATE agents
                SET {', '.join(columns)},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                params,
            )
        if cur.rowcount != 1:
            return None
        return self.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        """Delete an agent row and return True when a row was removed."""
        with _transaction(self.conn):
            cur = self.conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        return cur.rowcount == 1

    def update_state(self, agent_id: str, state: str, *, last_output_hash: str | None = None) -> bool:
        """Update an agent state and optional output hash."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE agents
                SET state = ?,
                    last_output_hash = COALESCE(?, last_output_hash),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (state, last_output_hash, agent_id),
            )
        return cur.rowcount == 1

    def update_health(self, agent_id: str, health: str, *, details: object | None = None) -> bool:
        """Update agent health and append a health event audit row."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE agents SET health = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (health, agent_id),
            )
            if cur.rowcount == 1:
                self.conn.execute(
                    "INSERT INTO health_events (agent_id, event_type, details) VALUES (?, ?, ?)",
                    (agent_id, health, _json_dumps(details)),
                )
        return cur.rowcount == 1

    def record_heartbeat(self, agent_id: str, *, last_output_hash: str | None = None) -> bool:
        """Record a heartbeat timestamp and optional output hash for an agent."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE agents
                SET last_heartbeat = CURRENT_TIMESTAMP,
                    last_output_hash = COALESCE(?, last_output_hash),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (last_output_hash, agent_id),
            )
        return cur.rowcount == 1

    def update_metrics(self, agent_id: str, duration_seconds: int) -> bool:
        """Update rolling average task duration and increment completed task count."""
        row = self.conn.execute(
            "SELECT avg_task_seconds, tasks_completed FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        if row is None:
            return False
        completed = int(row["tasks_completed"] or 0)
        current_avg = row["avg_task_seconds"]
        if current_avg is None or completed == 0:
            new_avg = int(duration_seconds)
        else:
            new_avg = round(((int(current_avg) * completed) + int(duration_seconds)) / (completed + 1))
        with _transaction(self.conn):
            self.conn.execute(
                """
                UPDATE agents
                SET avg_task_seconds = ?, tasks_completed = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_avg, completed + 1, agent_id),
            )
        return True


class TaskRepo:
    """Persistence operations for task queue lifecycle and CAS claiming."""

    def __init__(self, conn: Any) -> None:
        """Create a task repository bound to an existing database connection."""
        self.conn = conn

    def create(
        self,
        title: str,
        prompt: str,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        description: str | None = None,
        priority: int = 2,
        assigned_to: str | None = None,
        depends_on: list[str] | None = None,
        created_by: str | None = None,
        max_retries: int = 3,
        timeout_seconds: int = 1800,
        estimate_minutes: int | None = None,
        subtasks: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
    ) -> str:
        """Create a queued task and return its ID."""
        task_id = task_id or new_id("task-")
        progress = {"done": []}
        with _transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO tasks (
                    id, project_id, title, description, prompt, priority, assigned_to, depends_on,
                    created_by, max_retries, timeout_seconds, estimate_minutes, subtasks, progress,
                    acceptance_criteria
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    project_id,
                    title,
                    description,
                    prompt,
                    priority,
                    assigned_to,
                    _json_dumps(depends_on or []),
                    created_by,
                    max_retries,
                    timeout_seconds,
                    estimate_minutes,
                    _json_dumps(subtasks or []),
                    _json_dumps(progress),
                    _json_dumps(acceptance_criteria or []),
                ),
            )
        self._write_audit(task_id, created_by, "created", notes=f"assigned_to={assigned_to or ''}")
        return task_id

    def get(self, task_id: str) -> dict[str, object] | None:
        """Return one task by ID, or None when it does not exist."""
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_dict(row, {"depends_on", "subtasks", "progress", "acceptance_criteria"})

    def list(
        self,
        *,
        state: str | None = None,
        assigned_to: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return tasks filtered by state, assignee, and project ID."""
        clauses: list[str] = []
        params: list[object] = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        if assigned_to is not None:
            clauses.append("assigned_to = ?")
            params.append(assigned_to)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY priority ASC, created_at ASC, id ASC",
            params,
        ).fetchall()
        return _rows_to_dicts(rows, {"depends_on", "subtasks", "progress", "acceptance_criteria"})

    def update_state(self, task_id: str, state: str) -> bool:
        """Update a task lifecycle state."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE tasks SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (state, task_id),
            )
        return cur.rowcount == 1

    def set_blocked(self, task_id: str, reason: str) -> bool:
        """Mark a task as blocked with a specific reason."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE tasks SET state = 'blocked', blocked_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (reason, task_id),
            )
        return cur.rowcount == 1

    def claim(self, task_id: str, agent_id: str, expected_version: int) -> bool:
        """Atomically claim a task using the version column as a compare-and-swap guard."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE tasks
                SET state = 'assigned', assigned_to = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ?
                """,
                (agent_id, task_id, expected_version),
            )
        return cur.rowcount == 1

    def set_dispatched(self, task_id: str, *, dispatched_at: str | None = None) -> bool:
        """Mark a task as dispatched and set its dispatch timestamp."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE tasks
                SET state = 'dispatched', dispatched_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (dispatched_at or utc_now(), task_id),
            )
        return cur.rowcount == 1

    def checkin(self, task_id: str, agent_id: str) -> bool:
        """Record the moment an agent starts working on a task (checkin timestamp)."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE tasks
                SET state = 'in_progress', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (task_id,),
            )
        if cur.rowcount == 1:
            self._write_audit(task_id, agent_id, "checkin")
        return cur.rowcount == 1

    def complete(self, task_id: str, *, duration_seconds: int | None = None, completed_by: str | None = None, evidence: str | None = None) -> bool:
        """Mark a task done with full audit trail: timestamp, agent, and evidence of delivery."""
        task = self.get(task_id)
        if task and not duration_seconds:
            started = task.get("started_at") or task.get("dispatched_at")
            if started:
                from datetime import datetime, UTC
                try:
                    start_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                    duration_seconds = int((datetime.now(UTC) - start_dt).total_seconds())
                except Exception:
                    pass
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE tasks
                SET state = 'done', completed_at = CURRENT_TIMESTAMP,
                    completed_by = ?, evidence = ?,
                    duration_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (completed_by, evidence, duration_seconds, task_id),
            )
        if cur.rowcount == 1:
            self._write_audit(task_id, completed_by, "checkout", evidence=evidence)
        return cur.rowcount == 1

    def fail(self, task_id: str, error_message: str, *, state: str = "failed", agent_id: str | None = None) -> bool:
        """Mark a task as failed or timed out, persist error message, and write audit log."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE tasks
                SET state = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (state, error_message, task_id),
            )
        if cur.rowcount == 1:
            self._write_audit(task_id, agent_id, "failed", notes=error_message[:500])
        return cur.rowcount == 1

    def progress_subtask(self, task_id: str, subtask: str, *, done: bool = True, agent_id: str | None = None) -> bool:
        """Mark one OTTL subtask as done or open and recompute progress JSON."""
        task = self.get(task_id)
        if task is None:
            return False
        subtasks = [str(item) for item in (task.get("subtasks") or [])]
        if not subtasks:
            subtasks = [subtask]
        if subtask.isdigit():
            index = int(subtask)
            if index < 0 or index >= len(subtasks):
                raise IndexError(f"subtask index out of range: {subtask}")
            subtask_key = subtasks[index]
        else:
            subtask_key = subtask
            if subtask_key not in subtasks:
                subtasks.append(subtask_key)
        progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
        done_items = {str(item) for item in progress.get("done", []) if item is not None}
        if done:
            done_items.add(subtask_key)
        else:
            done_items.discard(subtask_key)
        payload = {"done": sorted(done_items)}
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE tasks
                SET subtasks = ?, progress = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (_json_dumps(subtasks), _json_dumps(payload), task_id),
            )
        if cur.rowcount == 1:
            self._write_audit(task_id, agent_id, "progress", notes=f"{subtask_key}={'done' if done else 'open'}")
        return cur.rowcount == 1

    def upsert_alert(self, alert_type: str, message: str, *, task_id: str | None = None, agent_id: str | None = None) -> dict[str, object]:
        """Create or refresh an active OTTL alert."""
        with _transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO task_alerts (task_id, agent_id, alert_type, message, active, updated_at)
                VALUES (?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (task_id, agent_id, alert_type) DO UPDATE SET
                    message = EXCLUDED.message,
                    active = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, agent_id, alert_type, message),
            )
        row = self.conn.execute(
            """
            SELECT * FROM task_alerts
            WHERE COALESCE(task_id, '') = COALESCE(?, '')
              AND COALESCE(agent_id, '') = COALESCE(?, '')
              AND alert_type = ?
            """,
            (task_id, agent_id, alert_type),
        ).fetchone()
        return _row_to_dict(row) or {}

    def list_alerts(self, *, active: bool | None = True) -> list[dict[str, object]]:
        """Return OTTL alerts."""
        if active is None:
            rows = self.conn.execute("SELECT * FROM task_alerts ORDER BY updated_at DESC, id DESC").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM task_alerts WHERE active = ? ORDER BY updated_at DESC, id DESC",
                (active,),
            ).fetchall()
        return _rows_to_dicts(rows)

    def _write_audit(self, task_id: str, agent_id: str | None, event: str, *, evidence: str | None = None, notes: str | None = None) -> None:
        """Write a row to the task_audit_log table."""
        try:
            with _transaction(self.conn):
                self.conn.execute(
                    "INSERT INTO task_audit_log (task_id, agent_id, event, evidence, notes) VALUES (?, ?, ?, ?, ?)",
                    (task_id, agent_id, event, evidence, notes),
                )
            _mirror_task_event_to_ledger(task_id, agent_id, event, evidence=evidence, notes=notes)
        except Exception:
            try:
                self.conn.rollback()
            except Exception:
                pass
            pass  # Audit log failure must never break the primary flow

    def increment_retry(self, task_id: str) -> bool:
        """Increment a task retry count."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE tasks SET retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id,),
            )
        return cur.rowcount == 1

    def list_ready(self) -> list[dict[str, object]]:
        """Return queued tasks whose dependencies are all completed."""
        queued = self.list(state="queued")
        ready: list[dict[str, object]] = []
        for task in queued:
            dependencies = task.get("depends_on") or []
            if not isinstance(dependencies, list):
                dependencies = []
            if self._dependencies_done([str(dep) for dep in dependencies]):
                ready.append(task)
        return ready

    def _dependencies_done(self, task_ids: list[str]) -> bool:
        if not task_ids:
            return True
        placeholders = ",".join("?" for _ in task_ids)
        rows = self.conn.execute(
            f"SELECT id, state FROM tasks WHERE id IN ({placeholders})",
            task_ids,
        ).fetchall()
        states = {row["id"]: row["state"] for row in rows}
        return all(states.get(task_id) == "done" for task_id in task_ids)


def _mirror_task_event_to_ledger(
    task_id: str,
    agent_id: str | None,
    event: str,
    *,
    evidence: str | None = None,
    notes: str | None = None,
) -> None:
    """Append DB task lifecycle events to the human GSD ledger."""
    ledger = Path(
        os.environ.get(
            "HERDMASTER_LEDGER_PATH",
            "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/CHECKIN_OUT_GSD.md",
        )
    )
    timestamp = utc_now()
    action = {
        "created": "TASK-CREATE",
        "checkin": "TASK-CHECK-IN",
        "checkout": "TASK-CHECK-OUT",
        "failed": "TASK-FAILED",
        "progress": "TASK-PROGRESS",
    }.get(event, f"TASK-{event.upper()}")
    detail = evidence or notes or "DB mirrored event"
    line = (
        f"| {timestamp} | {agent_id or 'herdmaster'} | {action} | {task_id} | HerdMaster tasks DB | "
        f"MIRRORED | {detail} |\n"
    )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(line)


class MessageRepo:
    """Persistence operations for the message audit log."""

    def __init__(self, conn: Any) -> None:
        """Create a message repository bound to an existing database connection."""
        self.conn = conn

    def insert(
        self,
        message_type: str,
        payload: object,
        *,
        message_id: str | None = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
        correlation_id: str | None = None,
        ttl_seconds: int | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Insert a message and return its ID."""
        message_id = message_id or new_id("msg-")
        if expires_at is None and ttl_seconds is not None:
            expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with _transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO messages (id, type, from_agent, to_agent, correlation_id, payload, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, message_type, from_agent, to_agent, correlation_id, _json_dumps(payload), expires_at),
            )
        return message_id

    def list(self, *, to_agent: str | None = None, delivered: bool | None = None) -> list[dict[str, object]]:
        """Return messages filtered by recipient and delivery status."""
        clauses: list[str] = []
        params: list[object] = []
        if to_agent is not None:
            clauses.append("to_agent = ?")
            params.append(to_agent)
        if delivered is not None:
            clauses.append("delivered = ?")
            params.append(delivered)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM messages {where} ORDER BY created_at ASC, id ASC",
            params,
        ).fetchall()
        return _rows_to_dicts(rows, {"payload"})

    def mark_delivered(self, message_id: str) -> bool:
        """Mark a message as delivered."""
        with _transaction(self.conn):
            cur = self.conn.execute("UPDATE messages SET delivered = TRUE WHERE id = ?", (message_id,))
        return cur.rowcount == 1

    def mark_acknowledged(self, message_id: str) -> bool:
        """Mark a message as acknowledged."""
        with _transaction(self.conn):
            cur = self.conn.execute("UPDATE messages SET acknowledged = TRUE WHERE id = ?", (message_id,))
        return cur.rowcount == 1

    def expire(self, *, now: str | None = None) -> int:
        """Delete undelivered messages whose expiration timestamp has passed and return the count."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                "DELETE FROM messages WHERE delivered = FALSE AND expires_at IS NOT NULL AND expires_at <= ?",
                (now or utc_now(),),
            )
        return cur.rowcount


class ProjectRepo:
    """Persistence operations for project mode and historical ETA learning."""

    def __init__(self, conn: Any) -> None:
        """Create a project repository bound to an existing database connection."""
        self.conn = conn

    def create(
        self,
        name: str,
        scope: str,
        *,
        project_id: str | None = None,
        deadline: str | None = None,
        complexity_tier: str | None = None,
        created_by: str | None = None,
    ) -> str:
        """Create a project in submitted state and return its ID."""
        project_id = project_id or new_id("proj-")
        with _transaction(self.conn):
            self.conn.execute(
                """
                INSERT INTO projects (id, name, scope, deadline, complexity_tier, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, name, scope, deadline, complexity_tier, created_by),
            )
        return project_id

    def get(self, project_id: str) -> dict[str, object] | None:
        """Return one project by ID, or None when it does not exist."""
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _row_to_dict(row, {"squad_recommendation", "squad_approved", "orchestrator_analysis"})

    def list(self, *, state: str | None = None) -> list[dict[str, object]]:
        """Return projects, optionally filtered by state."""
        if state is None:
            rows = self.conn.execute("SELECT * FROM projects ORDER BY created_at DESC, id DESC").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM projects WHERE state = ? ORDER BY created_at DESC, id DESC",
                (state,),
            ).fetchall()
        return _rows_to_dicts(rows, {"squad_recommendation", "squad_approved", "orchestrator_analysis"})

    def update_state(self, project_id: str, state: str) -> bool:
        """Update a project state."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                "UPDATE projects SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (state, project_id),
            )
        return cur.rowcount == 1

    def set_analysis(
        self,
        project_id: str,
        analysis: object,
        *,
        complexity_tier: str | None = None,
        squad_recommendation: object | None = None,
    ) -> bool:
        """Persist orchestrator analysis JSON, optional complexity tier, and optional squad recommendation."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE projects
                SET orchestrator_analysis = ?,
                    complexity_tier = COALESCE(?, complexity_tier),
                    squad_recommendation = COALESCE(?, squad_recommendation),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (_json_dumps(analysis), complexity_tier, _json_dumps(squad_recommendation), project_id),
            )
        return cur.rowcount == 1

    def set_squad(
        self,
        project_id: str,
        squad: object,
        *,
        human_decision: str | None = None,
        human_notes: str | None = None,
        approved: bool = False,
    ) -> bool:
        """Persist the approved squad and optional human decision metadata."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE projects
                SET squad_approved = ?,
                    human_decision = COALESCE(?, human_decision),
                    human_notes = COALESCE(?, human_notes),
                    approved_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE approved_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (_json_dumps(squad), human_decision, human_notes, approved, project_id),
            )
        return cur.rowcount == 1

    def set_eta(
        self,
        project_id: str,
        *,
        optimistic_hours: float | None = None,
        expected_hours: float | None = None,
        pessimistic_hours: float | None = None,
        rationale: str | None = None,
    ) -> bool:
        """Persist ETA estimate fields for a project."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                UPDATE projects
                SET eta_optimistic_hours = ?,
                    eta_expected_hours = ?,
                    eta_pessimistic_hours = ?,
                    eta_rationale = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (optimistic_hours, expected_hours, pessimistic_hours, rationale, project_id),
            )
        return cur.rowcount == 1

    def update_progress(self, project_id: str) -> bool:
        """Recompute project progress counters from child tasks and update project completion state."""
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END) AS completed_tasks,
                SUM(CASE WHEN state IN ('failed', 'timeout') THEN 1 ELSE 0 END) AS failed_tasks
            FROM tasks
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        total = int(row["total_tasks"] or 0)
        completed = int(row["completed_tasks"] or 0)
        failed = int(row["failed_tasks"] or 0)
        completed_at_expr = "CURRENT_TIMESTAMP" if total > 0 and completed + failed == total else "completed_at"
        state_expr = "'completed'" if total > 0 and completed == total else "state"
        with _transaction(self.conn):
            cur = self.conn.execute(
                f"""
                UPDATE projects
                SET total_tasks = ?, completed_tasks = ?, failed_tasks = ?,
                    completed_at = {completed_at_expr}, state = {state_expr}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (total, completed, failed, project_id),
            )
        return cur.rowcount == 1

    def insert_history(
        self,
        project_id: str,
        *,
        complexity_tier: str | None,
        total_tasks: int | None,
        agents_used: int | None,
        estimated_hours: float | None,
        actual_hours: float | None,
        accuracy_pct: float | None = None,
    ) -> int:
        """Insert a project history row for future ETA learning and return its row ID."""
        with _transaction(self.conn):
            cur = self.conn.execute(
                """
                INSERT INTO project_history (
                    project_id, complexity_tier, total_tasks, agents_used,
                    estimated_hours, actual_hours, accuracy_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (project_id, complexity_tier, total_tasks, agents_used, estimated_hours, actual_hours, accuracy_pct),
            )
            row_id = int(cur.lastrowid)
        return row_id

    def complexity_lookup(self, complexity_tier: str) -> list[dict[str, object]]:
        """Return historical project records for a complexity tier ordered newest first."""
        rows = self.conn.execute(
            """
            SELECT * FROM project_history
            WHERE complexity_tier = ?
            ORDER BY completed_at DESC, id DESC
            """,
            (complexity_tier,),
        ).fetchall()
        return _rows_to_dicts(rows)

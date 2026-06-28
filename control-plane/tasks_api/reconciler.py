"""Reconciler that bridges squad-tasks.json, Postgres, and HerdMaster.

The reconciler is the core of TD5-OTTL. It performs a one-shot sync:

1. Read ``ops/squad-tasks.json`` (the TL-managed ledger).
2. Upsert every task into the Postgres ``ottl_tasks`` table.
3. For each task with a ``herdmaster_task_id`` in metadata, fetch the
   live state from HerdMaster and update ``herdmaster_state``.

The reconciler is designed to be invoked:
- Manually via ``POST /api/tasks/reconcile``.
- Automatically on startup (optional, via ``AOP_OTTL_AUTO_RECONCILE``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import TaskPriority, TaskStatus
from .repository import TaskRepository

logger = logging.getLogger(__name__)

# Map squad-tasks.json status values to our TaskStatus enum.
_STATUS_MAP: dict[str, TaskStatus] = {
    "pending": TaskStatus.PENDING,
    "working": TaskStatus.WORKING,
    "review": TaskStatus.REVIEW,
    "held": TaskStatus.HELD,
    "blocked": TaskStatus.BLOCKED,
    "orphaned": TaskStatus.ORPHANED,
    "done": TaskStatus.DONE,
}

# Map HerdMaster task states to a normalised string for herdmaster_state.
_HM_STATE_MAP: dict[str, str] = {
    "queued": "queued",
    "claimed": "claimed",
    "in_progress": "in_progress",
    "done": "done",
    "failed": "failed",
    "blocked": "blocked",
}


class TaskReconciler:
    """Sync the squad-tasks.json ledger and HerdMaster state into Postgres."""

    def __init__(
        self,
        repository: TaskRepository,
        *,
        squad_tasks_path: str | Path | None = None,
        herdmaster_client: Any | None = None,
    ) -> None:
        self.repo = repository
        self.squad_tasks_path = Path(squad_tasks_path) if squad_tasks_path else None
        self.herdmaster_client = herdmaster_client

    def reconcile_from_file(self, path: str | Path | None = None) -> dict[str, Any]:
        """Read squad-tasks.json and upsert all tasks into Postgres.

        Returns a summary dict with counts.
        """
        source = Path(path) if path else self.squad_tasks_path
        if source is None or not source.exists():
            return {"reconciled": 0, "errors": [f"squad-tasks.json not found at {source}"]}

        data = json.loads(source.read_text(encoding="utf-8"))
        tasks = data.get("tasks", []) if isinstance(data, dict) else data
        if not isinstance(tasks, list):
            return {"reconciled": 0, "errors": ["invalid squad-tasks.json: expected 'tasks' array"]}

        count = 0
        errors: list[str] = []
        for entry in tasks:
            try:
                self._upsert_task(entry)
                count += 1
            except Exception as exc:
                task_id = entry.get("id", "?")
                errors.append(f"task {task_id}: {exc}")
                logger.warning("reconcile failed for task %s: %s", task_id, exc)

        return {"reconciled": count, "errors": errors, "source": str(source)}

    def _upsert_task(self, entry: dict[str, Any]) -> None:
        """Convert a squad-tasks.json entry and upsert it."""
        task_id = str(entry["id"])
        status_str = str(entry.get("status", "pending"))
        status = _STATUS_MAP.get(status_str, TaskStatus.PENDING)
        priority_str = str(entry.get("priority", "P2"))
        try:
            priority = TaskPriority(priority_str)
        except ValueError:
            priority = TaskPriority.P2

        metadata = dict(entry.get("metadata", {}))
        # Preserve raw agent/pane from the ledger entry
        agent = str(entry.get("agent", "unknown"))
        pane = str(entry.get("pane", ""))
        herdmaster_task_id = metadata.get("herdmaster_task_id")

        self.repo.upsert(
            task_id=task_id,
            title=str(entry.get("title", "")),
            priority=priority,
            agent=agent,
            pane=pane,
            status=status,
            eta_min=int(entry.get("eta_min", 0)),
            progress=int(entry.get("progress", 0)),
            herdmaster_task_id=herdmaster_task_id,
            metadata=metadata,
        )

    def sync_herdmaster_states(self) -> dict[str, Any]:
        """For each task with a herdmaster_task_id, fetch and update the live state.

        Uses the provided HerdMasterAuthClient (or any object implementing
        ``poll``). Tasks without a herdmaster_task_id are skipped.
        """
        if self.herdmaster_client is None:
            return {"synced": 0, "errors": ["no herdmaster client configured"]}

        all_tasks = self.repo.list()
        synced = 0
        errors: list[str] = []
        for task in all_tasks:
            if not task.herdmaster_task_id:
                continue
            try:
                import asyncio

                result = asyncio.run(self._poll_herdmaster(task.herdmaster_task_id))
                state = self._normalize_hm_state(result)
                self.repo.update(
                    task.task_id,
                    herdmaster_state=state,
                )
                synced += 1
            except Exception as exc:
                errors.append(f"task {task.task_id}: {exc}")
                logger.warning("herdmaster sync failed for task %s: %s", task.task_id, exc)

        return {"synced": synced, "errors": errors}

    async def _poll_herdmaster(self, herdmaster_task_id: str) -> dict[str, Any]:
        """Poll a single HerdMaster task by ID. Returns the raw response dict."""
        # Build a minimal TaskEnvelope-like object for the poll() interface.
        # The HerdMasterAuthClient.poll() only reads task_id from the envelope.
        from core import OperationMode, TaskBudget, TaskEnvelope

        envelope = TaskEnvelope(
            task_id=herdmaster_task_id,
            tenant_id="reconcile",
            project_id="reconcile",
            assignee_runtime="reconcile",
            prompt="reconcile herdmaster task state",
            credential_ref="seat://local",
            operation_mode=OperationMode.SOCKET,
            budget=TaskBudget(),
        )
        return await self.herdmaster_client.poll(envelope)

    def _normalize_hm_state(self, result: dict[str, Any]) -> str:
        """Extract a normalised state string from a HerdMaster poll response."""
        # HerdMaster returns {"ok": true, "data": {"state": "...", ...}}
        # or a flat dict with "state".
        data = result.get("data", result) if isinstance(result, dict) else {}
        raw_state = str(data.get("state", data.get("status", "unknown")))
        return _HM_STATE_MAP.get(raw_state, raw_state)

    def reconcile_all(self) -> dict[str, Any]:
        """Full reconciliation: file sync + HerdMaster state sync."""
        file_result = self.reconcile_from_file()
        hm_result = self.sync_herdmaster_states()
        return {
            "file": file_result,
            "herdmaster": hm_result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

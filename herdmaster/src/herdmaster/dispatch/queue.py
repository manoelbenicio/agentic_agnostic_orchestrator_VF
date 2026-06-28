"""Task queue state machine and atomic claiming support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from string import Formatter
from typing import Any

from herdmaster.db.repositories import AgentRepo, TaskRepo


PRIORITIES: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}

TERMINAL_STATES = {"done", "failed", "timeout", "cancelled"}


class TaskStateError(RuntimeError):
    """Raised when a task lifecycle transition is not allowed."""


@dataclass(frozen=True, slots=True)
class ReassignResult:
    """Result of a retry/reassignment decision."""

    task_id: str
    reassigned: bool
    escalated: bool
    retry_count: int
    max_retries: int


@dataclass(frozen=True, slots=True)
class _Template:
    title: str
    prompt: str
    description: str | None
    priority: int
    depends_on: tuple[str, ...]
    max_retries: int
    timeout_seconds: int


class TaskQueue:
    """High-level task queue wrapper over an injected :class:`TaskRepo`.

    Templates are intentionally in-memory for FR-208. They are useful for the
    current process, but callers that need durable templates should persist the
    template definitions outside this class and register them at startup.
    """

    def __init__(self, task_repo: TaskRepo, agent_repo: AgentRepo | None = None) -> None:
        """Create a queue without opening new database connections."""

        self.task_repo = task_repo
        self.agent_repo = agent_repo
        self._claim_lock = asyncio.Lock()
        self._templates: dict[str, _Template] = {}

    def enqueue(
        self,
        title: str,
        prompt: str,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        description: str | None = None,
        priority: str | int = "normal",
        assigned_to: str | None = None,
        depends_on: list[str] | None = None,
        created_by: str | None = None,
        max_retries: int = 3,
        timeout_seconds: int = 1800,
        estimate_minutes: int | None = None,
        subtasks: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
    ) -> str:
        """Insert a queued task and return its task ID."""

        return self.task_repo.create(
            title=title,
            prompt=prompt,
            task_id=task_id,
            project_id=project_id,
            description=description,
            priority=_priority_value(priority),
            assigned_to=assigned_to,
            depends_on=depends_on,
            created_by=created_by,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            estimate_minutes=estimate_minutes,
            subtasks=subtasks,
            acceptance_criteria=acceptance_criteria,
        )

    def ready_tasks(self) -> list[dict[str, object]]:
        """Return queued tasks whose dependencies are done, ordered by priority then FIFO."""

        return sorted(
            self.task_repo.list_ready(),
            key=lambda task: (
                int(task.get("priority")) if task.get("priority") is not None else PRIORITIES["normal"],
                str(task.get("created_at") or ""),
                str(task.get("id") or ""),
            ),
        )

    async def claim_next(self, agent_id: str) -> dict[str, object] | None:
        """Atomically claim the next ready task for an agent.

        The event-loop lock serializes callers sharing this queue instance, and
        ``TaskRepo.claim`` supplies the database-level CAS guard for concurrent
        queue instances or processes.
        """

        async with self._claim_lock:
            for task in self.ready_tasks():
                task_id = str(task["id"])
                version = int(task.get("version") or 0)
                if self.task_repo.claim(task_id, agent_id, version):
                    return self.task_repo.get(task_id)
            return None

    def mark_dispatched(self, task_id: str) -> dict[str, object]:
        """Transition ``assigned`` to ``dispatched``."""

        self._require_state(task_id, {"assigned"}, "dispatched")
        if not self.task_repo.set_dispatched(task_id):
            raise KeyError(task_id)
        return self._get(task_id)

    def mark_in_progress(self, task_id: str) -> dict[str, object]:
        """Transition ``dispatched`` to ``in_progress``."""

        self._require_state(task_id, {"dispatched"}, "in_progress")
        self._set_state(task_id, "in_progress")
        return self._get(task_id)

    def mark_done(self, task_id: str, *, duration_seconds: int | None = None) -> dict[str, object]:
        """Transition ``in_progress`` to ``done``."""

        self._require_state(task_id, {"in_progress"}, "done")
        if not self.task_repo.complete(task_id, duration_seconds=duration_seconds):
            raise KeyError(task_id)
        return self._get(task_id)

    def mark_failed(self, task_id: str, error_message: str) -> dict[str, object]:
        """Transition ``in_progress`` to ``failed``."""

        self._require_state(task_id, {"in_progress"}, "failed")
        if not self.task_repo.fail(task_id, error_message, state="failed"):
            raise KeyError(task_id)
        return self._get(task_id)

    def mark_timeout(self, task_id: str, error_message: str = "task timed out") -> dict[str, object]:
        """Transition ``in_progress`` to ``timeout``."""

        self._require_state(task_id, {"in_progress"}, "timeout")
        if not self.task_repo.fail(task_id, error_message, state="timeout"):
            raise KeyError(task_id)
        return self._get(task_id)

    def cancel(self, task_id: str) -> dict[str, object]:
        """Cancel a non-terminal task."""

        task = self._get(task_id)
        state = str(task.get("state") or "")
        if state in TERMINAL_STATES:
            raise TaskStateError(f"cannot cancel task {task_id!r} from terminal state {state!r}")
        self._set_state(task_id, "cancelled")
        return self._get(task_id)

    def reassign(self, task_id: str) -> ReassignResult:
        """Return a failed or timed-out task to ``queued`` until retries are exhausted.

        When ``retry_count`` is already at ``max_retries``, the task is left in
        place and the returned result sets ``escalated=True`` so the caller can
        alert a human through the message bus layer.
        """

        task = self._get(task_id)
        state = str(task.get("state") or "")
        if state not in {"failed", "timeout"}:
            raise TaskStateError(f"cannot reassign task {task_id!r} from state {state!r}")

        retry_count = int(task.get("retry_count") or 0)
        max_retries = int(task.get("max_retries") or 0)
        if retry_count >= max_retries:
            return ReassignResult(task_id, False, True, retry_count, max_retries)

        if not self.task_repo.increment_retry(task_id):
            raise KeyError(task_id)
        updated = self._get(task_id)
        new_retry_count = int(updated.get("retry_count") or retry_count + 1)
        self.task_repo.conn.execute(
            """
            UPDATE tasks
            SET state = 'queued',
                assigned_to = NULL,
                dispatched_at = NULL,
                completed_at = NULL,
                error_message = NULL,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (task_id,),
        )
        self.task_repo.conn.commit()
        return ReassignResult(task_id, True, False, new_retry_count, max_retries)

    def register_template(
        self,
        name: str,
        *,
        title: str,
        prompt: str,
        description: str | None = None,
        priority: str | int = "normal",
        depends_on: list[str] | None = None,
        max_retries: int = 3,
        timeout_seconds: int = 1800,
    ) -> None:
        """Register an in-memory prompt template using ``str.format`` fields."""

        if not name:
            raise ValueError("template name must not be empty")
        self._templates[name] = _Template(
            title=title,
            prompt=prompt,
            description=description,
            priority=_priority_value(priority),
            depends_on=tuple(depends_on or ()),
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )

    def from_template(
        self,
        name: str,
        variables: dict[str, Any] | None = None,
        **enqueue_overrides: object,
    ) -> str:
        """Render a registered template and enqueue the resulting task."""

        template = self._templates[name]
        values = variables or {}
        _validate_template_values(template.title, values)
        _validate_template_values(template.prompt, values)
        description = template.description
        if description is not None:
            _validate_template_values(description, values)
            description = description.format(**values)

        payload: dict[str, object] = {
            "title": template.title.format(**values),
            "prompt": template.prompt.format(**values),
            "description": description,
            "priority": template.priority,
            "depends_on": list(template.depends_on),
            "max_retries": template.max_retries,
            "timeout_seconds": template.timeout_seconds,
        }
        payload.update(enqueue_overrides)
        return self.enqueue(**payload)

    def _require_state(self, task_id: str, allowed: set[str], target: str) -> dict[str, object]:
        task = self._get(task_id)
        state = str(task.get("state") or "")
        if state not in allowed:
            allowed_states = ", ".join(sorted(allowed))
            raise TaskStateError(
                f"cannot transition task {task_id!r} from {state!r} to {target!r}; "
                f"expected one of: {allowed_states}"
            )
        return task

    def _set_state(self, task_id: str, state: str) -> None:
        if not self.task_repo.update_state(task_id, state):
            raise KeyError(task_id)

    def _get(self, task_id: str) -> dict[str, object]:
        task = self.task_repo.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task


def _priority_value(priority: str | int) -> int:
    if isinstance(priority, int):
        if priority < 0:
            raise ValueError("priority must be non-negative")
        return priority
    normalized = priority.lower()
    if normalized not in PRIORITIES:
        raise ValueError(f"unknown priority {priority!r}")
    return PRIORITIES[normalized]


def _validate_template_values(template: str, values: dict[str, Any]) -> None:
    missing = [
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name and field_name.split(".", 1)[0].split("[", 1)[0] not in values
    ]
    if missing:
        raise KeyError(", ".join(sorted(set(missing))))

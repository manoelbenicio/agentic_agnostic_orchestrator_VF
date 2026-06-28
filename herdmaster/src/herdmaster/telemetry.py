"""Orchestration telemetry, task board, and drift reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import fnmatch
import json
from pathlib import Path
from typing import Any

from herdmaster.db.repositories import AgentRepo, MessageRepo, TaskRepo


ALERT_TL_NO_DISPATCH = "TL_NO_DISPATCH"
ALERT_AGENT_NO_CHECKIN = "AGENT_NO_CHECKIN"
ALERT_UNTRACKED_WORK = "UNTRACKED_WORK"
ALERT_STALLED = "STALLED"
ALERT_SCOPE_DRIFT = "SCOPE_DRIFT"
ALERT_INVALID_COMPLETION = "INVALID_COMPLETION"

ALERT_TYPES = {
    ALERT_TL_NO_DISPATCH,
    ALERT_AGENT_NO_CHECKIN,
    ALERT_UNTRACKED_WORK,
    ALERT_STALLED,
    ALERT_SCOPE_DRIFT,
    ALERT_INVALID_COMPLETION,
}


@dataclass(frozen=True, slots=True)
class ReconcileConfig:
    """Thresholds used by OTTL reconciliation."""

    checkin_grace_minutes: int = 10
    stale_heartbeat_minutes: int = 15
    prompt_dir: Path | None = None
    tl_agent_id: str = "cli"


def task_progress(task: dict[str, Any]) -> dict[str, Any]:
    """Return objective progress and ETA for one task."""
    subtasks = [str(item) for item in (task.get("subtasks") or [])]
    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    done_set = {str(item) for item in progress.get("done", [])}
    total = len(subtasks)
    done = len([item for item in subtasks if item in done_set]) if total else 0
    percent = int(round((done / total) * 100)) if total else (100 if str(task.get("state")) == "done" else 0)

    elapsed_minutes = _elapsed_minutes(task)
    estimate = task.get("estimate_minutes")
    try:
        estimate_minutes = int(estimate) if estimate is not None else None
    except (TypeError, ValueError):
        estimate_minutes = None
    eta_plan = max(0, estimate_minutes - elapsed_minutes) if estimate_minutes is not None else None
    eta_vel = None
    if done > 0 and total > done:
        eta_vel = int(round(((total - done) / done) * elapsed_minutes))
    return {
        "subtasks_total": total,
        "subtasks_done": done,
        "percent": percent,
        "elapsed_minutes": elapsed_minutes,
        "eta_plan_minutes": eta_plan,
        "eta_velocity_minutes": eta_vel,
    }


def build_board(
    tasks: TaskRepo,
    agents: AgentRepo,
    *,
    messages: MessageRepo | None = None,
    config: ReconcileConfig | None = None,
) -> dict[str, Any]:
    """Reconcile telemetry and return board rows grouped by agent."""
    alerts = reconcile(tasks, agents, messages=messages, config=config)
    active_alerts = tasks.list_alerts(active=True)
    alert_lookup: dict[tuple[str | None, str | None], list[str]] = {}
    for alert in active_alerts:
        key = (_optional(alert.get("task_id")), _optional(alert.get("agent_id")))
        alert_lookup.setdefault(key, []).append(str(alert.get("alert_type")))

    task_rows = tasks.list()
    rows: list[dict[str, Any]] = []
    for task in task_rows:
        task_id = str(task.get("id"))
        agent_id = _optional(task.get("assigned_to"))
        progress = task_progress(task)
        flags = sorted(set(alert_lookup.get((task_id, agent_id), []) + alert_lookup.get((task_id, None), [])))
        rows.append(
            {
                "task_id": task_id,
                "title": task.get("title"),
                "agent_id": agent_id,
                "state": task.get("state"),
                "progress": progress["percent"],
                "elapsed_minutes": progress["elapsed_minutes"],
                "eta_plan_minutes": progress["eta_plan_minutes"],
                "eta_velocity_minutes": progress["eta_velocity_minutes"],
                "last_heartbeat": _agent_heartbeat(agents, agent_id),
                "evidence": bool(task.get("evidence")),
                "flags": flags,
            }
        )

    agent_rows: list[dict[str, Any]] = []
    for agent in agents.list():
        agent_id = str(agent.get("id"))
        current = [row for row in rows if row.get("agent_id") == agent_id and row.get("state") == "in_progress"]
        flags = sorted(set(alert_lookup.get((None, agent_id), [])))
        for row in rows:
            if row.get("agent_id") == agent_id:
                flags.extend(row.get("flags", []))
        agent_rows.append(
            {
                "agent_id": agent_id,
                "label": agent.get("label"),
                "state": agent.get("state"),
                "health": agent.get("health"),
                "last_heartbeat": agent.get("last_heartbeat"),
                "task": current[0] if current else None,
                "flags": sorted(set(flags)),
            }
        )
    return {"tasks": rows, "agents": agent_rows, "alerts": active_alerts, "emitted": alerts}


def reconcile(
    tasks: TaskRepo,
    agents: AgentRepo,
    *,
    messages: MessageRepo | None = None,
    config: ReconcileConfig | None = None,
) -> list[dict[str, object]]:
    """Run OTTL reconciliation checks and persist active alerts."""
    cfg = config or ReconcileConfig()
    now = datetime.now(UTC)
    emitted: list[dict[str, object]] = []
    all_tasks = tasks.list()
    all_agents = agents.list()

    for task in all_tasks:
        state = str(task.get("state") or "")
        task_id = str(task.get("id"))
        agent_id = _optional(task.get("assigned_to"))
        updated = _parse_dt(task.get("updated_at") or task.get("created_at"))
        started = _parse_dt(task.get("started_at"))
        if state == "assigned" and agent_id and updated and now - updated > timedelta(minutes=cfg.checkin_grace_minutes):
            emitted.append(_alert(tasks, messages, ALERT_AGENT_NO_CHECKIN, f"{agent_id} has not checked in", task_id=task_id, agent_id=agent_id, tl_agent_id=cfg.tl_agent_id))
        if state == "in_progress" and agent_id:
            agent = agents.get(agent_id)
            heartbeat = _parse_dt(agent.get("last_heartbeat")) if agent else None
            agent_state = str(agent.get("state") or "") if agent else "missing"
            if agent_state in {"idle", "done", "unknown"} or (heartbeat and now - heartbeat > timedelta(minutes=cfg.stale_heartbeat_minutes)):
                emitted.append(_alert(tasks, messages, ALERT_STALLED, f"{task_id} is in progress but {agent_id} is {agent_state}", task_id=task_id, agent_id=agent_id, tl_agent_id=cfg.tl_agent_id))
            if _scope_drift(tasks, task, agent_id):
                emitted.append(_alert(tasks, messages, ALERT_SCOPE_DRIFT, f"{agent_id} activity is outside task scope", task_id=task_id, agent_id=agent_id, tl_agent_id=cfg.tl_agent_id))
        if state in {"done", "complete", "completed"} and not _valid_evidence(task.get("evidence")):
            emitted.append(_alert(tasks, messages, ALERT_INVALID_COMPLETION, f"{task_id} completed without screenshot/SHA/test evidence", task_id=task_id, agent_id=agent_id, tl_agent_id=cfg.tl_agent_id))

    for agent in all_agents:
        agent_id = str(agent.get("id"))
        if str(agent.get("state") or "") == "working":
            current = [task for task in all_tasks if task.get("assigned_to") == agent_id and task.get("state") == "in_progress"]
            if not current:
                emitted.append(_alert(tasks, messages, ALERT_UNTRACKED_WORK, f"{agent_id} is working without an in-progress task", agent_id=agent_id, tl_agent_id=cfg.tl_agent_id))

    for prompt_file in _orphan_prompt_files(cfg.prompt_dir, all_tasks):
        emitted.append(_alert(tasks, messages, ALERT_TL_NO_DISPATCH, f"prompt injection has no matching task: {prompt_file}", tl_agent_id=cfg.tl_agent_id))
    return emitted


def _alert(
    tasks: TaskRepo,
    messages: MessageRepo | None,
    alert_type: str,
    message: str,
    *,
    task_id: str | None = None,
    agent_id: str | None = None,
    tl_agent_id: str = "cli",
) -> dict[str, object]:
    alert = tasks.upsert_alert(alert_type, message, task_id=task_id, agent_id=agent_id)
    if messages is not None:
        messages.insert(
            "alert",
            {"alert_type": alert_type, "task_id": task_id, "agent_id": agent_id, "message": message},
            from_agent="ottl-reconciler",
            to_agent=tl_agent_id,
        )
    return alert


def _scope_drift(tasks: TaskRepo, task: dict[str, Any], agent_id: str) -> bool:
    criteria = [str(item) for item in (task.get("acceptance_criteria") or [])]
    patterns = [item.split("scope:", 1)[1].strip() for item in criteria if item.startswith("scope:")]
    if not patterns:
        return False
    row = tasks.conn.execute(
        """
        SELECT details FROM health_events
        WHERE agent_id = ? AND details IS NOT NULL
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (agent_id,),
    ).fetchone()
    if not row:
        return False
    try:
        details = json.loads(str(row["details"]))
    except (TypeError, ValueError):
        return False
    path = str(details.get("path") or details.get("file") or details.get("topic") or "")
    return bool(path) and not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _valid_evidence(value: object) -> bool:
    text = str(value or "").lower()
    return bool(text) and (".png" in text or "print" in text or "screenshot" in text) and "sha" in text and ("test" in text or "pytest" in text)


def _orphan_prompt_files(prompt_dir: Path | None, tasks: list[dict[str, object]]) -> list[str]:
    if prompt_dir is None or not prompt_dir.exists():
        return []
    known = {str(task.get("id")) for task in tasks}
    orphaned: list[str] = []
    for path in prompt_dir.glob("*.md"):
        if path.stem not in known:
            orphaned.append(str(path))
    return orphaned


def _elapsed_minutes(task: dict[str, Any]) -> int:
    start = _parse_dt(task.get("started_at") or task.get("dispatched_at") or task.get("created_at"))
    end = _parse_dt(task.get("completed_at")) or datetime.now(UTC)
    if start is None:
        return 0
    return max(0, int((end - start).total_seconds() // 60))


def _agent_heartbeat(agents: AgentRepo, agent_id: str | None) -> object:
    if not agent_id:
        return None
    agent = agents.get(agent_id)
    return agent.get("last_heartbeat") if agent else None


def _parse_dt(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _optional(value: object) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)

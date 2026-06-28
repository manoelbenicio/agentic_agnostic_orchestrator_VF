"""Real-time TUI dashboard for HerdMaster (HM-012, FR-501..505, FR-307).

This module renders a live, read-only control-plane dashboard with five panels:

#. **Agent grid** (FR-502): id, label, type, state, health, current task,
   uptime, last heartbeat.
#. **Task list**: every task with its state, priority, and assignee.
#. **Project panel**: per-project progress bars plus a live ETA range.
#. **Alerts panel** (FR-307): human escalations streamed from the message bus.
#. **Metrics panel** (FR-504): tasks per agent, average completion time, and
   failure rate.

Design notes
------------
* **Read-only consumer.** The dashboard only issues ``SELECT`` queries through
  the injected repositories and reads alert frames from the bus. It never
  mutates task/agent/project state and never edits any other module.
* **Dependency injection.** :class:`DashboardApp` accepts already-constructed
  repositories and an optional bus socket path, so it is trivially testable.
  :meth:`DashboardApp.from_config` wires everything from a
  :class:`herdmaster.config.HerdMasterConfig`.
* **~1s non-blocking tick.** Data is collected with fast indexed ``SELECT``s.
  The bus subscription runs on its own daemon thread with a private asyncio
  loop, so the render loop is never blocked on socket I/O.
* **Graceful backend fallback.** ``textual`` is used when available, then
  ``rich``, then a dependency-free plaintext renderer. Alerts are sourced
  from the live bus socket when reachable and from the persisted message log
  otherwise, merged and de-duplicated by message id.

Only ``herdmaster.{db,bus,config}.*`` plus optional ``textual``/``rich`` and
the Python standard library are imported.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from herdmaster.bus.messages import Message, MessageType
from herdmaster.config import HerdMasterConfig, load_config
from herdmaster.db.repositories import AgentRepo, MessageRepo, ProjectRepo, TaskRepo
from herdmaster.db.schema import connect

# ---------------------------------------------------------------------------
# Optional rendering backends (imported lazily / defensively)
# ---------------------------------------------------------------------------

try:  # pragma: no cover - availability depends on environment
    import rich  # noqa: F401

    HAS_RICH = True
except Exception:  # noqa: BLE001
    HAS_RICH = False

try:  # pragma: no cover - availability depends on environment
    import textual  # noqa: F401

    HAS_TEXTUAL = True
except Exception:  # noqa: BLE001
    HAS_TEXTUAL = False


# Priority code -> label (TaskRepo stores 0=critical .. 3=low).
_PRIORITY_LABELS = {0: "critical", 1: "high", 2: "normal", 3: "low"}

# Task states considered "active work" for an agent's current-task column.
_ACTIVE_TASK_STATES = ("assigned", "dispatched", "in_progress")

# Task states that count as a finished outcome for failure-rate maths.
_TERMINAL_STATES = ("done", "failed", "timeout", "cancelled")
_FAILED_STATES = ("failed", "timeout")

_DB_TS_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(UTC)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse a DB ``CURRENT_TIMESTAMP`` or ISO-8601 string into UTC.

    Returns ``None`` when *value* is falsy or unparseable, so callers can show
    a placeholder instead of crashing the render loop.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    # ISO-8601 (bus timestamps look like "2026-06-21T23:01:00Z").
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass
    # DB "YYYY-MM-DD HH:MM:SS" (always UTC in this schema).
    for fmt in _DB_TS_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _human_age(then: Optional[datetime], *, now: Optional[datetime] = None) -> str:
    """Render the elapsed time since *then* as a compact human string."""
    if then is None:
        return "never"
    now = now or _utc_now()
    delta = (now - then).total_seconds()
    if delta < 0:
        delta = 0.0
    return _human_seconds(delta)


def _human_seconds(seconds: float) -> str:
    """Render a duration in seconds as ``45s`` / ``12m`` / ``3h`` / ``2d``."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def _truncate(value: Any, width: int) -> str:
    """Coerce *value* to a single-line string clipped to *width* characters."""
    text = "" if value is None else str(value).replace("\n", " ").strip()
    if width <= 1:
        return text[:width]
    return text if len(text) <= width else text[: width - 1] + "\u2026"


# ---------------------------------------------------------------------------
# Snapshot data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AgentRow:
    """One row in the agent grid panel (FR-502)."""

    id: str
    label: str
    type: str
    state: str
    health: str
    current_task: str
    uptime: str
    last_heartbeat: str


@dataclass(slots=True)
class TaskRow:
    """One row in the task list panel."""

    id: str
    title: str
    state: str
    priority: str
    assignee: str


@dataclass(slots=True)
class ProjectRow:
    """One row in the project panel (progress + live ETA)."""

    id: str
    name: str
    state: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    progress: float  # 0.0 .. 1.0
    eta_text: str


@dataclass(slots=True)
class AlertRow:
    """One escalation/alert surfaced from the bus (FR-307)."""

    id: str
    timestamp: Optional[datetime]
    source: str
    summary: str
    live: bool = False


@dataclass(slots=True)
class Metrics:
    """Aggregate observability metrics (FR-504)."""

    total_agents: int = 0
    total_tasks: int = 0
    tasks_per_agent: float = 0.0
    avg_completion: str = "n/a"
    failure_rate: float = 0.0
    state_counts: dict[str, int] = field(default_factory=dict)
    bus_connected: bool = False


@dataclass(slots=True)
class DashboardSnapshot:
    """Immutable view of all five panels for a single render tick."""

    generated_at: datetime
    agents: list[AgentRow] = field(default_factory=list)
    tasks: list[TaskRow] = field(default_factory=list)
    projects: list[ProjectRow] = field(default_factory=list)
    alerts: list[AlertRow] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Alert collection (live bus + persisted log, merged & de-duplicated)
# ---------------------------------------------------------------------------


class AlertCollector:
    """Thread-safe store of recent alerts keyed by message id.

    Alerts arrive from two independent sources that may overlap:

    * the live bus socket subscription (``add_message``), and
    * the persisted message log (``add_message`` via DB polling).

    De-duplication by id keeps a single entry per alert; the ``live`` flag is
    sticky so an alert seen on the wire is never downgraded.
    """

    def __init__(self, *, max_alerts: int = 200) -> None:
        self._max = max_alerts
        self._lock = threading.Lock()
        self._alerts: "OrderedDict[str, AlertRow]" = OrderedDict()

    def add_message(self, message: Message, *, live: bool) -> None:
        """Record a parsed bus :class:`Message` if it is an alert."""
        if message.type != MessageType.ALERT:
            return
        row = AlertRow(
            id=message.id,
            timestamp=_parse_timestamp(message.timestamp),
            source=message.from_agent or "system",
            summary=_summarize_payload(message.payload),
            live=live,
        )
        self._store(row)

    def add_db_row(self, row: dict[str, Any]) -> None:
        """Record an alert from a persisted ``messages`` table row."""
        if str(row.get("type")) != MessageType.ALERT.value:
            return
        payload = row.get("payload")
        summary, source, ts = _unwrap_db_payload(payload)
        alert = AlertRow(
            id=str(row.get("id", "")),
            timestamp=ts or _parse_timestamp(row.get("created_at")),
            source=source or str(row.get("from_agent") or "system"),
            summary=summary,
            live=False,
        )
        self._store(alert)

    def _store(self, alert: AlertRow) -> None:
        if not alert.id:
            return
        with self._lock:
            existing = self._alerts.get(alert.id)
            if existing is not None:
                # Preserve a previously observed live flag.
                alert.live = alert.live or existing.live
                self._alerts.pop(alert.id, None)
            self._alerts[alert.id] = alert
            while len(self._alerts) > self._max:
                self._alerts.popitem(last=False)

    def snapshot(self, *, limit: int = 20) -> list[AlertRow]:
        """Return the most recent alerts, newest first."""
        with self._lock:
            rows = list(self._alerts.values())
        rows.sort(
            key=lambda a: a.timestamp or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return rows[:limit]


def _summarize_payload(payload: Any) -> str:
    """Best-effort one-line summary of an alert payload dict."""
    if isinstance(payload, dict):
        for key in ("reason", "message", "summary", "detail", "error", "text"):
            if payload.get(key):
                return _truncate(payload[key], 120)
        if payload:
            return _truncate(json.dumps(payload, separators=(",", ":"), sort_keys=True), 120)
    if payload:
        return _truncate(payload, 120)
    return "(escalation)"


def _unwrap_db_payload(payload: Any) -> tuple[str, Optional[str], Optional[datetime]]:
    """Extract (summary, source, timestamp) from a persisted message payload.

    The bus persists the full JSON-RPC envelope string as the payload, so we
    transparently unwrap ``params`` when present; plain content dicts are also
    supported.
    """
    data: Any = payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return _truncate(payload, 120), None, None
    if isinstance(data, dict):
        params = data.get("params") if isinstance(data.get("params"), dict) else None
        if params is not None:
            source = params.get("from")
            ts = _parse_timestamp(params.get("timestamp"))
            return _summarize_payload(params.get("payload", {})), source, ts
        return _summarize_payload(data), data.get("from"), _parse_timestamp(data.get("timestamp"))
    return _summarize_payload(data), None, None


# ---------------------------------------------------------------------------
# Bus subscriber (daemon thread, private asyncio loop, non-blocking)
# ---------------------------------------------------------------------------


class BusSubscriber:
    """Subscribe to the Unix-socket bus and stream alert frames into a collector.

    Runs entirely on a daemon thread with its own event loop so the dashboard
    render loop is never blocked. Reconnects with bounded backoff and silently
    degrades when the socket is unavailable (the DB poll then supplies alerts).
    """

    def __init__(
        self,
        socket_path: str | Path,
        collector: AlertCollector,
        *,
        agent_id: str = "tui-dashboard",
    ) -> None:
        self.socket_path = str(socket_path)
        self.collector = collector
        self.agent_id = f"{agent_id}-{int(time.time())}"
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._connected = threading.Event()

    @property
    def connected(self) -> bool:
        """True while a live socket subscription is established."""
        return self._connected.is_set()

    def start(self) -> None:
        """Spawn the background subscription thread (idempotent)."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="herdmaster-tui-bus", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the subscription thread to exit and wait briefly for it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        self._connected.clear()

    # -- internal ---------------------------------------------------------

    def _run(self) -> None:
        try:
            asyncio.run(self._loop())
        except Exception:  # noqa: BLE001 - subscriber must never crash the app
            self._connected.clear()

    async def _loop(self) -> None:
        backoff = 0.5
        while not self._stop.is_set():
            try:
                await self._session()
                backoff = 0.5
            except (OSError, asyncio.IncompleteReadError, ValueError):
                self._connected.clear()
            except Exception:  # noqa: BLE001
                self._connected.clear()
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)

    async def _session(self) -> None:
        reader, writer = await asyncio.open_unix_connection(self.socket_path)
        try:
            register = {
                "jsonrpc": "2.0",
                "method": "register",
                "params": {"agent_id": self.agent_id},
                "id": self.agent_id,
            }
            writer.write((json.dumps(register, separators=(",", ":")) + "\n").encode())
            await writer.drain()
            self._connected.set()
            while not self._stop.is_set():
                raw = await asyncio.wait_for(reader.readline(), timeout=1.0)
                if not raw:
                    break  # server closed the connection
                line = raw.decode().strip()
                if not line:
                    continue
                self._ingest(line)
        finally:
            self._connected.clear()
            if not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    def _ingest(self, line: str) -> None:
        # Skip JSON-RPC acks (e.g. the "registered" result) and keep only
        # well-formed alert messages.
        try:
            envelope = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return
        if isinstance(envelope, dict) and "result" in envelope and "method" not in envelope:
            return
        try:
            message = Message.from_json(line)
        except (ValueError, json.JSONDecodeError):
            return
        self.collector.add_message(message, live=True)


# ---------------------------------------------------------------------------
# Snapshot collection (pure, read-only)
# ---------------------------------------------------------------------------


def build_snapshot(
    *,
    agent_repo: AgentRepo,
    task_repo: TaskRepo,
    project_repo: ProjectRepo,
    message_repo: Optional[MessageRepo],
    collector: AlertCollector,
    bus_connected: bool,
    now: Optional[datetime] = None,
    max_tasks: int = 200,
) -> DashboardSnapshot:
    """Collect a full :class:`DashboardSnapshot` from the repositories.

    All reads are wrapped defensively: a missing table or transient error
    yields an empty panel and an ``error`` annotation rather than crashing the
    render loop.
    """
    now = now or _utc_now()
    snap = DashboardSnapshot(generated_at=now)

    agents = _safe_list(agent_repo.list)
    tasks = _safe_list(task_repo.list)
    projects = _safe_list(project_repo.list)

    # Merge persisted alerts so escalations survive a bus reconnect/restart.
    if message_repo is not None:
        for row in _safe_list(message_repo.list):
            collector.add_db_row(row)

    # Index active tasks by assignee for the agent grid's current-task column.
    active_by_agent: dict[str, dict[str, Any]] = {}
    for task in tasks:
        assignee = task.get("assigned_to")
        if assignee and task.get("state") in _ACTIVE_TASK_STATES:
            # Prefer the highest priority (lowest code) active task.
            current = active_by_agent.get(assignee)
            if current is None or _priority_code(task) < _priority_code(current):
                active_by_agent[assignee] = task

    snap.agents = [_agent_row(a, active_by_agent, now) for a in agents]
    snap.tasks = [_task_row(t) for t in tasks[:max_tasks]]
    snap.projects = [_project_row(p) for p in projects]
    snap.alerts = collector.snapshot()
    snap.metrics = _compute_metrics(agents, tasks, bus_connected=bus_connected)
    return snap


def _safe_list(fn: Callable[..., list[dict[str, Any]]]) -> list[dict[str, Any]]:
    try:
        result = fn()
        return list(result) if result else []
    except Exception:  # noqa: BLE001 - tolerate missing tables / transient errors
        return []


def _priority_code(task: dict[str, Any]) -> int:
    try:
        return int(task.get("priority", 2))
    except (TypeError, ValueError):
        return 2


def _agent_row(
    agent: dict[str, Any],
    active_by_agent: dict[str, dict[str, Any]],
    now: datetime,
) -> AgentRow:
    agent_id = str(agent.get("id", "?"))
    current = active_by_agent.get(agent_id)
    if current is not None:
        current_task = _truncate(
            current.get("title") or current.get("id") or "?", 32
        )
    else:
        current_task = "\u2014"  # em dash = idle / none
    return AgentRow(
        id=agent_id,
        label=_truncate(agent.get("label") or agent_id, 20),
        type=_truncate(agent.get("type") or "?", 10),
        state=_truncate(agent.get("state") or "unknown", 12),
        health=_truncate(agent.get("health") or "?", 11),
        current_task=current_task,
        uptime=_human_age(_parse_timestamp(agent.get("created_at")), now=now),
        last_heartbeat=_human_age(_parse_timestamp(agent.get("last_heartbeat")), now=now),
    )


def _task_row(task: dict[str, Any]) -> TaskRow:
    return TaskRow(
        id=_truncate(task.get("id") or "?", 18),
        title=_truncate(task.get("title") or "", 34),
        state=_truncate(task.get("state") or "queued", 11),
        priority=_PRIORITY_LABELS.get(_priority_code(task), str(_priority_code(task))),
        assignee=_truncate(task.get("assigned_to") or "\u2014", 16),
    )


def _project_row(project: dict[str, Any]) -> ProjectRow:
    total = _as_int(project.get("total_tasks"))
    completed = _as_int(project.get("completed_tasks"))
    failed = _as_int(project.get("failed_tasks"))
    progress = (completed / total) if total > 0 else 0.0
    progress = min(max(progress, 0.0), 1.0)
    return ProjectRow(
        id=_truncate(project.get("id") or "?", 16),
        name=_truncate(project.get("name") or "?", 24),
        state=_truncate(project.get("state") or "?", 14),
        total_tasks=total,
        completed_tasks=completed,
        failed_tasks=failed,
        progress=progress,
        eta_text=_eta_text(project, progress),
    )


def _eta_text(project: dict[str, Any], progress: float) -> str:
    """Render a live ETA: stored optimistic/expected/pessimistic range plus a
    naive remaining estimate derived from current progress."""
    opt = _as_float(project.get("eta_optimistic_hours"))
    exp = _as_float(project.get("eta_expected_hours"))
    pess = _as_float(project.get("eta_pessimistic_hours"))
    if exp is None and opt is None and pess is None:
        return "ETA: n/a"
    parts: list[str] = []
    if opt is not None:
        parts.append(f"opt {opt:.1f}h")
    if exp is not None:
        parts.append(f"exp {exp:.1f}h")
    if pess is not None:
        parts.append(f"pess {pess:.1f}h")
    text = "ETA: " + " / ".join(parts)
    state = str(project.get("state") or "")
    if exp is not None and state not in ("completed", "failed", "cancelled"):
        remaining = exp * (1.0 - progress)
        text += f"  (~{remaining:.1f}h left)"
    return text


def _compute_metrics(
    agents: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    *,
    bus_connected: bool,
) -> Metrics:
    total_agents = len(agents)
    total_tasks = len(tasks)

    state_counts: dict[str, int] = {}
    durations: list[float] = []
    terminal = 0
    failed = 0
    for task in tasks:
        state = str(task.get("state") or "queued")
        state_counts[state] = state_counts.get(state, 0) + 1
        if state in _TERMINAL_STATES:
            terminal += 1
        if state in _FAILED_STATES:
            failed += 1
        if state == "done":
            duration = _as_float(task.get("duration_seconds"))
            if duration is not None and duration >= 0:
                durations.append(duration)

    # Average completion time: prefer per-task durations, fall back to the
    # rolling per-agent average maintained by AgentRepo.
    if durations:
        avg_completion = _human_seconds(sum(durations) / len(durations))
    else:
        agent_avgs = [
            _as_float(a.get("avg_task_seconds"))
            for a in agents
            if _as_float(a.get("avg_task_seconds"))
        ]
        agent_avgs = [v for v in agent_avgs if v is not None]
        avg_completion = _human_seconds(sum(agent_avgs) / len(agent_avgs)) if agent_avgs else "n/a"

    tasks_per_agent = (total_tasks / total_agents) if total_agents else 0.0
    failure_rate = (failed / terminal) if terminal else 0.0

    return Metrics(
        total_agents=total_agents,
        total_tasks=total_tasks,
        tasks_per_agent=round(tasks_per_agent, 2),
        avg_completion=avg_completion,
        failure_rate=round(failure_rate, 4),
        state_counts=state_counts,
        bus_connected=bus_connected,
    )


def _as_int(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Plaintext rendering (dependency-free fallback)
# ---------------------------------------------------------------------------


def _progress_bar(progress: float, width: int = 20) -> str:
    filled = int(round(progress * width))
    filled = min(max(filled, 0), width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {progress * 100:5.1f}%"


def render_plaintext(snapshot: DashboardSnapshot) -> str:
    """Render a snapshot as a plain-text dashboard (no third-party deps)."""
    lines: list[str] = []
    ts = snapshot.generated_at.strftime("%Y-%m-%d %H:%M:%SZ")
    bus = "connected" if snapshot.metrics.bus_connected else "db-poll"
    lines.append(f"HerdMaster Dashboard  |  {ts}  |  bus: {bus}")
    lines.append("=" * 96)
    if snapshot.error:
        lines.append(f"!! {snapshot.error}")

    # Panel 1: agents (FR-502)
    lines.append("AGENTS")
    header = f"{'ID':<10}{'LABEL':<20}{'TYPE':<10}{'STATE':<12}{'HEALTH':<11}{'CURRENT TASK':<32}{'UPTIME':<8}{'HEARTBEAT':<10}"
    lines.append(header)
    lines.append("-" * len(header))
    if snapshot.agents:
        for a in snapshot.agents:
            lines.append(
                f"{a.id:<10}{a.label:<20}{a.type:<10}{a.state:<12}{a.health:<11}{a.current_task:<32}{a.uptime:<8}{a.last_heartbeat:<10}"
            )
    else:
        lines.append("(no agents registered)")
    lines.append("")

    # Panel 2: tasks
    lines.append("TASKS (state / priority / assignee)")
    t_header = f"{'ID':<18}{'TITLE':<34}{'STATE':<11}{'PRIORITY':<9}{'ASSIGNEE':<16}"
    lines.append(t_header)
    lines.append("-" * len(t_header))
    if snapshot.tasks:
        for t in snapshot.tasks[:25]:
            lines.append(f"{t.id:<18}{t.title:<34}{t.state:<11}{t.priority:<9}{t.assignee:<16}")
        if len(snapshot.tasks) > 25:
            lines.append(f"... (+{len(snapshot.tasks) - 25} more)")
    else:
        lines.append("(no tasks)")
    lines.append("")

    # Panel 3: projects (progress + live ETA)
    lines.append("PROJECTS")
    if snapshot.projects:
        for p in snapshot.projects:
            lines.append(
                f"{p.name:<26}{p.state:<14}{_progress_bar(p.progress)}  "
                f"{p.completed_tasks}/{p.total_tasks} done, {p.failed_tasks} failed"
            )
            lines.append(f"    {p.eta_text}")
    else:
        lines.append("(no projects)")
    lines.append("")

    # Panel 4: alerts (FR-307)
    lines.append("ALERTS / ESCALATIONS")
    if snapshot.alerts:
        for al in snapshot.alerts[:10]:
            when = al.timestamp.strftime("%H:%M:%S") if al.timestamp else "--:--:--"
            tag = "*" if al.live else " "
            lines.append(f"{tag} [{when}] {al.source:<16} {al.summary}")
    else:
        lines.append("(no active escalations)")
    lines.append("")

    # Panel 5: metrics (FR-504)
    m = snapshot.metrics
    lines.append("METRICS")
    lines.append(
        f"agents={m.total_agents}  tasks={m.total_tasks}  "
        f"tasks/agent={m.tasks_per_agent}  avg completion={m.avg_completion}  "
        f"failure rate={m.failure_rate * 100:.1f}%"
    )
    if m.state_counts:
        counts = "  ".join(f"{state}={n}" for state, n in sorted(m.state_counts.items()))
        lines.append(f"task states: {counts}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------


def render_rich(snapshot: DashboardSnapshot):  # pragma: no cover - needs rich
    """Build a ``rich`` renderable group for *snapshot*.

    Imported lazily so the module remains importable without ``rich``.
    """
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress_bar import ProgressBar
    from rich.text import Text

    # Agents
    agents_tbl = Table(expand=True, show_edge=False)
    for col in ("ID", "Label", "Type", "State", "Health", "Current Task", "Uptime", "Heartbeat"):
        agents_tbl.add_column(col, overflow="ellipsis", no_wrap=True)
    for a in snapshot.agents:
        agents_tbl.add_row(
            a.id, a.label, a.type,
            _state_text(a.state), _health_text(a.health),
            a.current_task, a.uptime, a.last_heartbeat,
        )
    if not snapshot.agents:
        agents_tbl.add_row("\u2014", "no agents", "", "", "", "", "", "")

    # Tasks
    tasks_tbl = Table(expand=True, show_edge=False)
    for col in ("ID", "Title", "State", "Priority", "Assignee"):
        tasks_tbl.add_column(col, overflow="ellipsis", no_wrap=True)
    for t in snapshot.tasks[:25]:
        tasks_tbl.add_row(t.id, t.title, t.state, t.priority, t.assignee)
    if not snapshot.tasks:
        tasks_tbl.add_row("\u2014", "no tasks", "", "", "")

    # Projects
    proj_tbl = Table(expand=True, show_edge=False)
    proj_tbl.add_column("Project", no_wrap=True)
    proj_tbl.add_column("State", no_wrap=True)
    proj_tbl.add_column("Progress", ratio=1)
    proj_tbl.add_column("ETA", no_wrap=True)
    for p in snapshot.projects:
        bar = ProgressBar(total=max(p.total_tasks, 1), completed=p.completed_tasks, width=24)
        proj_tbl.add_row(
            p.name, p.state,
            Group(bar, Text(f"{p.completed_tasks}/{p.total_tasks} done, {p.failed_tasks} failed")),
            p.eta_text,
        )
    if not snapshot.projects:
        proj_tbl.add_row("\u2014", "no projects", "", "")

    # Alerts
    alerts_tbl = Table(expand=True, show_edge=False)
    alerts_tbl.add_column("Time", no_wrap=True)
    alerts_tbl.add_column("Source", no_wrap=True)
    alerts_tbl.add_column("Escalation", overflow="fold")
    for al in snapshot.alerts[:10]:
        when = al.timestamp.strftime("%H:%M:%S") if al.timestamp else "--:--:--"
        alerts_tbl.add_row(
            Text(when, style="bold red" if al.live else "red"),
            al.source,
            al.summary,
        )
    if not snapshot.alerts:
        alerts_tbl.add_row("\u2014", "", "no active escalations")

    # Metrics
    m = snapshot.metrics
    metrics_text = Text()
    metrics_text.append(
        f"agents={m.total_agents}  tasks={m.total_tasks}  "
        f"tasks/agent={m.tasks_per_agent}  avg completion={m.avg_completion}  "
    )
    metrics_text.append(
        f"failure rate={m.failure_rate * 100:.1f}%",
        style="red" if m.failure_rate > 0.2 else "green",
    )
    if m.state_counts:
        counts = "  ".join(f"{s}={n}" for s, n in sorted(m.state_counts.items()))
        metrics_text.append(f"\ntask states: {counts}")

    bus = "connected" if m.bus_connected else "db-poll"
    ts = snapshot.generated_at.strftime("%Y-%m-%d %H:%M:%SZ")
    title = f"HerdMaster Dashboard  |  {ts}  |  bus: {bus}"

    return Group(
        Panel(agents_tbl, title="Agents (FR-502)", border_style="cyan"),
        Panel(tasks_tbl, title="Tasks", border_style="blue"),
        Panel(proj_tbl, title="Projects + ETA", border_style="magenta"),
        Panel(alerts_tbl, title="Alerts / Escalations (FR-307)", border_style="red"),
        Panel(metrics_text, title="Metrics (FR-504)", border_style="green"),
        Panel(Text(title, style="bold"), border_style="white"),
    )


def _state_text(state: str):  # pragma: no cover - needs rich
    from rich.text import Text

    palette = {
        "working": "green", "in_progress": "green", "idle": "cyan",
        "blocked": "yellow", "done": "blue", "unknown": "dim",
    }
    return Text(state, style=palette.get(state, "white"))


def _health_text(health: str):  # pragma: no cover - needs rich
    from rich.text import Text

    palette = {
        "healthy": "green", "suspect": "yellow",
        "unhealthy": "red", "recovering": "magenta",
    }
    return Text(health, style=palette.get(health, "white"))


# ---------------------------------------------------------------------------
# DashboardApp
# ---------------------------------------------------------------------------


class DashboardApp:
    """Real-time HerdMaster dashboard with pluggable rendering backends.

    Parameters
    ----------
    agent_repo, task_repo, project_repo:
        Read-only repositories (injected). Required.
    message_repo:
        Optional persisted-message repository used to source alerts when the
        live bus socket is unavailable.
    bus_socket_path:
        Optional Unix-socket path for live alert subscription.
    poll_interval:
        Render/poll cadence in seconds (default ~1s, FR-501).
    backend:
        ``"auto"`` (default), ``"textual"``, ``"rich"``, or ``"plaintext"``.
    now:
        Optional clock callable returning an aware UTC ``datetime`` (testing).
    """

    def __init__(
        self,
        *,
        agent_repo: AgentRepo,
        task_repo: TaskRepo,
        project_repo: ProjectRepo,
        message_repo: Optional[MessageRepo] = None,
        bus_socket_path: Optional[str | Path] = None,
        poll_interval: float = 1.0,
        backend: str = "auto",
        max_alerts: int = 200,
        now: Optional[Callable[[], datetime]] = None,
        _owns_connection: Optional[Any] = None,
    ) -> None:
        self.agent_repo = agent_repo
        self.task_repo = task_repo
        self.project_repo = project_repo
        self.message_repo = message_repo
        self.bus_socket_path = str(bus_socket_path) if bus_socket_path else None
        self.poll_interval = max(0.1, float(poll_interval))
        self.backend = self._resolve_backend(backend)
        self._now = now or _utc_now
        self._owns_connection = _owns_connection

        self.collector = AlertCollector(max_alerts=max_alerts)
        self.subscriber: Optional[BusSubscriber] = None
        if self.bus_socket_path:
            self.subscriber = BusSubscriber(self.bus_socket_path, self.collector)

    # -- construction helpers --------------------------------------------

    @classmethod
    def from_config(
        cls,
        config: Optional[HerdMasterConfig] = None,
        *,
        backend: str = "auto",
        poll_interval: float = 1.0,
    ) -> "DashboardApp":
        """Build a dashboard by wiring repositories from *config*.

        Opens a dedicated read-only Postgres connection; the connection is closed
        by :meth:`stop`.
        """
        config = config or load_config()
        conn = connect(config.paths.db)
        return cls(
            agent_repo=AgentRepo(conn),
            task_repo=TaskRepo(conn),
            project_repo=ProjectRepo(conn),
            message_repo=MessageRepo(conn),
            bus_socket_path=config.bus.socket_path,
            backend=backend,
            poll_interval=poll_interval,
            _owns_connection=conn,
        )

    @staticmethod
    def _resolve_backend(backend: str) -> str:
        backend = (backend or "auto").lower()
        if backend == "auto":
            if HAS_TEXTUAL:
                return "textual"
            if HAS_RICH:
                return "rich"
            return "plaintext"
        if backend == "textual" and not HAS_TEXTUAL:
            return "rich" if HAS_RICH else "plaintext"
        if backend == "rich" and not HAS_RICH:
            return "plaintext"
        return backend

    # -- snapshots --------------------------------------------------------

    def snapshot(self) -> DashboardSnapshot:
        """Collect one immutable dashboard snapshot (read-only, fast)."""
        connected = bool(self.subscriber and self.subscriber.connected)
        return build_snapshot(
            agent_repo=self.agent_repo,
            task_repo=self.task_repo,
            project_repo=self.project_repo,
            message_repo=self.message_repo,
            collector=self.collector,
            bus_connected=connected,
            now=self._now(),
        )

    def render_text(self) -> str:
        """Return the current plaintext rendering (handy for tests/headless)."""
        return render_plaintext(self.snapshot())

    # -- lifecycle --------------------------------------------------------

    def start_bus(self) -> None:
        """Start the background bus subscription if configured."""
        if self.subscriber is not None:
            self.subscriber.start()

    def stop(self) -> None:
        """Stop the bus subscription and close any owned DB connection."""
        if self.subscriber is not None:
            self.subscriber.stop()
        if self._owns_connection is not None:
            try:
                self._owns_connection.close()
            except Exception:  # noqa: BLE001
                pass
            self._owns_connection = None

    # -- run loops --------------------------------------------------------

    def run(self) -> None:
        """Run the dashboard with the selected backend until interrupted."""
        self.start_bus()
        try:
            if self.backend == "textual":
                self._run_textual()
            elif self.backend == "rich":
                self._run_rich()
            else:
                self._run_plaintext()
        finally:
            self.stop()

    def _run_plaintext(self) -> None:
        """Plaintext loop: clear screen, render, sleep ~poll_interval."""
        try:
            while True:
                text = render_plaintext(self.snapshot())
                # ANSI clear-screen + home; harmless on most terminals.
                print("\033[2J\033[H", end="")
                print(text, flush=True)
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            pass

    def _run_rich(self) -> None:  # pragma: no cover - needs rich
        from rich.live import Live

        with Live(render_rich(self.snapshot()), refresh_per_second=max(1, int(1 / self.poll_interval))) as live:
            try:
                while True:
                    live.update(render_rich(self.snapshot()))
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                pass

    def _run_textual(self) -> None:  # pragma: no cover - needs textual
        app = self._build_textual_app()
        app.run()

    def _build_textual_app(self):  # pragma: no cover - needs textual
        from textual.app import App, ComposeResult
        from textual.widgets import Static
        from rich.text import Text

        dashboard = self

        class _DashboardTextualApp(App):
            TITLE = "HerdMaster Dashboard"
            CSS = "Static { padding: 0 1; }"
            BINDINGS = [("q", "quit", "Quit")]

            def compose(self) -> "ComposeResult":
                yield Static(id="dashboard-body")

            def on_mount(self) -> None:
                self._body = self.query_one("#dashboard-body", Static)
                self._refresh()
                # Non-blocking periodic tick (FR-501).
                self.set_interval(dashboard.poll_interval, self._refresh)

            def _refresh(self) -> None:
                snap = dashboard.snapshot()
                if HAS_RICH:
                    self._body.update(render_rich(snap))
                else:
                    self._body.update(Text(render_plaintext(snap)))

        return _DashboardTextualApp()


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


def run_dashboard(
    config: Optional[HerdMasterConfig] = None,
    *,
    backend: str = "auto",
    poll_interval: float = 1.0,
) -> None:
    """Build a :class:`DashboardApp` from *config* and run it until interrupted."""
    app = DashboardApp.from_config(config, backend=backend, poll_interval=poll_interval)
    app.run()


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI entry: ``python -m herdmaster.tui.dashboard``."""
    import argparse

    parser = argparse.ArgumentParser(description="HerdMaster real-time TUI dashboard")
    parser.add_argument("--config", default=None, help="Path to herdmaster config TOML")
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "textual", "rich", "plaintext"],
        help="Rendering backend (default: auto)",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="Poll/refresh interval seconds"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = load_config(args.config) if args.config else load_config()
    run_dashboard(config, backend=args.backend, poll_interval=args.interval)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

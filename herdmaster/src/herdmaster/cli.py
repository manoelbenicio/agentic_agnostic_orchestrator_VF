"""HerdMaster command-line interface and runtime composition root."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import signal
from typing import Any


def _default_agent_id() -> str:
    """Return a sensible agent identity from the environment or fall back to 'cli'."""
    return os.environ.get("HERDMASTER_AGENT_ID") or "cli"

import typer
from rich.console import Console
from rich.table import Table

from herdmaster.acl.engine import AclEngine
from herdmaster.api.server import ControlApiServer
from herdmaster.bus.server import MessageBusServer
from herdmaster.config import ConfigError, HerdMasterConfig, load_config, setup_logging, validate_config
from herdmaster.db import repositories
from herdmaster.db.schema import connect, init_db
from herdmaster.dispatch.injector import DispatchInjector
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.herdr.adapter import HerdrAdapter
from herdmaster.project.planner import ProjectPlanner
from herdmaster.watchdog.engine import WatchdogEngine


console = Console()
app = typer.Typer(help="HerdMaster local control plane.")
tasks_app = typer.Typer(help="List, create, and cancel tasks.", no_args_is_help=True)
projects_app = typer.Typer(help="List, create, and approve projects.", no_args_is_help=True)
config_app = typer.Typer(help="Runtime configuration commands.", no_args_is_help=True)

JsonDict = dict[str, Any]
log = logging.getLogger(__name__)


class ControlPlaneUnavailable(RuntimeError):
    """Raised when the local Control API socket cannot be reached."""


@app.command()
def start(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    http: bool = typer.Option(False, "--http", help="Also start the localhost HTTP API."),
) -> None:
    """Start the HerdMaster control plane in the foreground."""

    try:
        asyncio.run(_run_control_plane(config_path, http_enabled=http))
    except ConfigError as exc:
        _fail(f"Configuration error: {exc}")
    except ValueError as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"Failed to start HerdMaster: {exc}")
    except KeyboardInterrupt:
        pass


@app.command()
def stop(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Stop a foreground-launched HerdMaster process using its PID file."""

    cfg = _load_valid_config(config_path)
    try:
        status_payload = _api_call_sync(cfg, "GET", "/status")
    except ControlPlaneUnavailable as exc:
        _api_down(exc)
    pid_file = _pid_file(cfg)
    if not pid_file.exists():
        _fail(f"Control plane is running, but no PID file was found at {pid_file}. Stop the foreground process with Ctrl-C.")
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
    except (ValueError, OSError) as exc:
        _fail(f"Failed to stop HerdMaster from PID file {pid_file}: {exc}")
    data = {"stopping": True, "pid": pid, "status": status_payload.get("data", {})}
    _print_json_or_message(data, json_output, f"Sent SIGTERM to HerdMaster process {pid}.")


@app.command()
def status(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Show control-plane health and uptime."""

    payload = _api_payload(config_path, "GET", "/status")
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    table = Table(title="HerdMaster Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("State", str(data.get("state", "unknown")))
    table.add_row("Started", str(data.get("started_at", "")))
    table.add_row("Uptime", _seconds_text(data.get("uptime_seconds")))
    agents = data.get("agents") if isinstance(data.get("agents"), dict) else {}
    tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}
    projects = data.get("projects") if isinstance(data.get("projects"), dict) else {}
    table.add_row("Agents", f"{agents.get('total', 0)} total, {agents.get('unhealthy', 0)} unhealthy")
    table.add_row("Tasks", ", ".join(f"{state}={count}" for state, count in sorted(tasks.items())) or "0")
    table.add_row("Projects", str(projects.get("total", 0)))
    transports = data.get("transports") if isinstance(data.get("transports"), dict) else {}
    table.add_row("API Socket", str(transports.get("unix", "")))
    console.print(table)


@app.command()
def agents(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """List known agents and their current state."""

    payload = _api_payload(config_path, "GET", "/agents")
    rows = _list_data(payload)
    if json_output:
        _print_json(rows)
        return
    table = Table(title="Agents")
    for column in ("ID", "Label", "Type", "Role", "State", "Health", "Current Task", "Heartbeat"):
        table.add_column(column)
    for agent in rows:
        current = agent.get("current_task") if isinstance(agent.get("current_task"), dict) else None
        table.add_row(
            str(agent.get("id", "")),
            str(agent.get("label", "")),
            str(agent.get("type", "")),
            str(agent.get("role", "")),
            str(agent.get("state", "")),
            str(agent.get("health", "")),
            str(current.get("title", "")) if current else "",
            str(agent.get("last_heartbeat", "") or ""),
        )
    console.print(table)


@app.command()
def metrics(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit parsed JSON output."),
) -> None:
    """Show control-plane metrics."""

    payload = _api_payload(config_path, "GET", "/metrics")
    text = str(payload.get("data") or "")
    parsed = _parse_prometheus_metrics(text)
    if json_output:
        _print_json(parsed)
        return
    table = Table(title="Metrics")
    table.add_column("Metric")
    table.add_column("Labels")
    table.add_column("Value", justify="right")
    for item in parsed:
        table.add_row(str(item["name"]), str(item["labels"]), str(item["value"]))
    console.print(table)


@tasks_app.command("list")
def list_tasks(
    state: str | None = typer.Option(None, "--state", help="Filter by task state."),
    assigned_to: str | None = typer.Option(None, "--assigned-to", help="Filter by agent ID."),
    project_id: str | None = typer.Option(None, "--project-id", help="Filter by project ID."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """List tasks."""

    query = _query(state=state, assigned_to=assigned_to, project_id=project_id)
    payload = _api_payload(config_path, "GET", "/tasks", query=query)
    rows = _list_data(payload)
    if json_output:
        _print_json(rows)
        return
    _render_tasks(rows)


@tasks_app.command("create")
def create_task(
    title: str = typer.Argument(..., help="Task title."),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt to dispatch to the agent."),
    description: str | None = typer.Option(None, "--description", "-d", help="Optional task description."),
    priority: str = typer.Option("normal", "--priority", help="critical, high, normal, or low."),
    assigned_to: str | None = typer.Option(None, "--assigned-to", help="Preferred agent ID."),
    project_id: str | None = typer.Option(None, "--project-id", help="Parent project ID."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Create a standalone or project task."""

    body = _query(
        title=title,
        prompt=prompt,
        description=description,
        priority=priority,
        assigned_to=assigned_to,
        project_id=project_id,
        created_by="cli",
    )
    payload = _api_payload(config_path, "POST", "/tasks", body=body)
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_tasks([data], title="Created Task")


@tasks_app.command("cancel")
def cancel_task(
    task_id: str = typer.Argument(..., help="Task ID to cancel."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Cancel a queued or active task."""

    payload = _api_payload(config_path, "DELETE", f"/tasks/{task_id}")
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_tasks([data], title="Cancelled Task")


@tasks_app.command("ask")
def ask_task(
    task_id: str = typer.Argument(..., help="Task ID that is blocked."),
    question: str = typer.Argument(..., help="The technical question or ambiguity encountered."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Block a task and ask the Orchestrator for clarification."""

    body = _query(reason=question)
    payload = _api_payload(config_path, "POST", f"/tasks/{task_id}/ask", body=body)
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_tasks([data], title="Blocked Task (Awaiting Orchestrator)")



@tasks_app.command("checkin")
def checkin_task(
    task_id: str = typer.Argument(..., help="Task ID to check in to."),
    agent_id: str = typer.Argument(None, help="Agent ID that is starting work (default: $HERDMASTER_AGENT_ID or 'cli')."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Record task start (checkin) — call this when an agent begins working."""

    agent_id = agent_id or _default_agent_id()
    body = _query(agent_id=agent_id)
    payload = _api_payload(config_path, "POST", f"/tasks/{task_id}/checkin", body=body)
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_tasks([data], title="Task Checkin Recorded")


@tasks_app.command("complete")
def complete_task(
    task_id: str = typer.Argument(..., help="Task ID to mark as complete."),
    agent_id: str = typer.Argument(None, help="Agent ID that completed the task (default: $HERDMASTER_AGENT_ID or 'cli')."),
    evidence: str = typer.Option("cli-completion", "--evidence", "-e", help="Evidence of delivery: file path, description, or screenshot path."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Record task completion (checkout) with delivery evidence — MANDATORY after every task."""

    agent_id = agent_id or _default_agent_id()
    body = _query(agent_id=agent_id, evidence=evidence)
    payload = _api_payload(config_path, "POST", f"/tasks/{task_id}/complete", body=body)
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_tasks([data], title="Task Completed")


@tasks_app.command("fail")
def fail_task(
    task_id: str = typer.Argument(..., help="Task ID to mark as failed."),
    agent_id: str = typer.Argument(None, help="Agent ID reporting the failure (default: $HERDMASTER_AGENT_ID or 'cli')."),
    reason: str = typer.Option("unspecified", "--reason", "-r", help="Precise description of what failed and why."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Report task failure with reason — MANDATORY on unrecoverable error."""

    agent_id = agent_id or _default_agent_id()
    body = _query(agent_id=agent_id, reason=reason)
    payload = _api_payload(config_path, "POST", f"/tasks/{task_id}/fail", body=body)
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_tasks([data], title="Task Failed")


@projects_app.command("list")
def list_projects(
    state: str | None = typer.Option(None, "--state", help="Filter by project state."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """List projects."""

    payload = _api_payload(config_path, "GET", "/projects", query=_query(state=state))
    rows = _list_data(payload)
    if json_output:
        _print_json(rows)
        return
    _render_projects(rows)


@projects_app.command("create")
def create_project(
    name: str = typer.Argument(..., help="Project name."),
    scope: str = typer.Option(..., "--scope", "-s", help="Full project scope prompt."),
    deadline: str | None = typer.Option(None, "--deadline", help="ISO-8601 deadline."),
    template: str | None = typer.Option(None, "--template", help="Project template name."),
    orchestrator_id: str | None = typer.Option(None, "--orchestrator-id", help="Agent ID to analyze the project."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Create and analyze a project, leaving it awaiting approval."""

    body = _query(
        name=name,
        scope=scope,
        deadline=deadline,
        template=template,
        orchestrator_id=orchestrator_id,
        created_by="cli",
    )
    payload = _api_payload(config_path, "POST", "/projects", body=body)
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    _render_projects([data], title="Created Project")


@projects_app.command("approve")
def approve_project(
    project_id: str = typer.Argument(..., help="Project ID to approve."),
    decision: str = typer.Option("accept", "--decision", help="accept, modify, or override."),
    notes: str | None = typer.Option(None, "--notes", help="Human approval notes."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Approve a project and enqueue its child tasks."""

    payload = _api_payload(
        config_path,
        "POST",
        f"/projects/{project_id}/approve",
        body=_query(decision=decision, human_notes=notes),
    )
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    task_ids = data.get("task_ids") if isinstance(data.get("task_ids"), list) else []
    _render_projects([project], title="Approved Project")
    console.print(f"Enqueued {len(task_ids)} task(s).")


@config_app.command("reload")
def reload_config(
    path: Path | None = typer.Option(None, "--path", help="Config path to reload inside the control plane."),
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config.toml for locating the API."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Hot-reload control-plane configuration."""

    payload = _api_payload(config_path, "POST", "/config/reload", body=_query(path=str(path) if path else None))
    data = dict(payload.get("data") or {})
    if json_output:
        _print_json(data)
        return
    console.print("Configuration reloaded.")


app.add_typer(tasks_app, name="tasks")
app.add_typer(projects_app, name="projects")
app.add_typer(config_app, name="config")


async def _run_control_plane(config_path: Path | None, *, http_enabled: bool) -> None:
    cfg = _load_valid_config(config_path)
    setup_logging(cfg.logging)
    cfg.paths.config_dir.mkdir(parents=True, exist_ok=True)
    control_socket = _control_socket_path(cfg)
    if await _api_available(cfg):
        raise ValueError(f"HerdMaster is already running at {control_socket}")

    pid_file = _pid_file(cfg)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    conn = connect(cfg.paths.db)
    init_db(conn)
    agents = repositories.AgentRepo(conn)
    agents.upsert("cli", "CLI Operator", "system", "observer", state="idle")

    # ADR-001 FR-AC-01/02: probe Herdr at boot (graceful degradation)
    from herdmaster.__main__ import _check_herdr_connection

    herdr_connected = await _check_herdr_connection(cfg)
    if herdr_connected:
        console.print("[green]Herdr connected.[/green]")
    else:
        console.print("[yellow]Herdr unavailable — running in degraded mode.[/yellow]")

    tasks = repositories.TaskRepo(conn)
    projects = repositories.ProjectRepo(conn)
    messages = repositories.MessageRepo(conn)
    queue = TaskQueue(tasks, agents)
    adapter = HerdrAdapter()
    bus = MessageBusServer(_bus_config(cfg), repo=messages)
    acl = AclEngine(cfg.acl)
    watchdog = WatchdogEngine(adapter, agents, cfg.watchdog, bus_publisher=bus, acl_config=cfg.acl)
    injector = DispatchInjector(adapter, queue, agents, cfg)
    planner = ProjectPlanner(projects, tasks, agents, queue, injector, adapter, cfg)

    def apply_reloaded_config(new_config: HerdMasterConfig) -> dict[str, str]:
        setup_logging(new_config.logging)
        watchdog.config = new_config.watchdog
        watchdog.acl_config = new_config.acl
        injector.config = replace(injector.config, fallback_dir=new_config.paths.config_dir / "prompts")
        return {"applied": "logging, watchdog, dispatch, acl"}

    api = ControlApiServer(
        config=cfg,
        planner=planner,
        queue=queue,
        agents=agents,
        tasks=tasks,
        projects=projects,
        messages=messages,
        bus=bus,
        acl=acl,
        socket_path=control_socket,
        http_enabled=http_enabled,
        reload_config=apply_reloaded_config,
    )
    dispatch_task: asyncio.Task[None] | None = None
    try:
        await bus.start()
        await watchdog.start()
        await api.start()
        dispatch_task = asyncio.create_task(_dispatch_loop(queue, injector, agents, stop_event))
        console.print(f"HerdMaster started. Control API: {control_socket}")
        await stop_event.wait()
    finally:
        if dispatch_task is not None:
            dispatch_task.cancel()
            with suppress(asyncio.CancelledError):
                await dispatch_task
        await _stop_service(api.stop())
        await _stop_service(watchdog.stop())
        await _stop_service(bus.stop())
        conn.close()
        with suppress(FileNotFoundError):
            pid_file.unlink()
        console.print("HerdMaster stopped.")


async def _dispatch_loop(
    queue: TaskQueue,
    injector: DispatchInjector,
    agents: repositories.AgentRepo,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            for agent in agents.list():
                if stop_event.is_set():
                    break
                agent_id = str(agent.get("id") or "")
                if not agent_id or str(agent.get("health") or "healthy") not in {"healthy", "recovering"}:
                    continue
                if str(agent.get("state") or "unknown") not in {"idle", "done", "unknown"}:
                    continue
                task = await queue.claim_next(agent_id)
                if task is not None:
                    await injector.dispatch(task)
        except Exception:
            log.exception("dispatch_loop_error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


async def _stop_service(awaitable: Awaitable[None]) -> None:
    try:
        await awaitable
    except Exception:
        log.exception("control_plane_shutdown_error")


async def _api_available(cfg: HerdMasterConfig) -> bool:
    try:
        await _api_call(cfg, "GET", "/status")
        return True
    except ControlPlaneUnavailable:
        return False


def _api_payload(
    config_path: Path | None,
    method: str,
    path: str,
    *,
    body: JsonDict | None = None,
    query: JsonDict | None = None,
) -> JsonDict:
    cfg = _load_valid_config(config_path)
    try:
        return _api_call_sync(cfg, method, path, body=body, query=query)
    except ControlPlaneUnavailable as exc:
        _api_down(exc)


def _api_call_sync(
    cfg: HerdMasterConfig,
    method: str,
    path: str,
    *,
    body: JsonDict | None = None,
    query: JsonDict | None = None,
) -> JsonDict:
    return asyncio.run(_api_call(cfg, method, path, body=body, query=query))


async def _api_call(
    cfg: HerdMasterConfig,
    method: str,
    path: str,
    *,
    body: JsonDict | None = None,
    query: JsonDict | None = None,
) -> JsonDict:
    socket_path = _control_socket_path(cfg)
    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
    except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
        raise ControlPlaneUnavailable(
            f"Control plane is not running at {socket_path}. Start it with 'herdmaster start'."
        ) from exc
    try:
        request = {"method": method.upper(), "path": path, "body": body or {}, "query": query or {}}
        writer.write((json.dumps(request, separators=(",", ":"), sort_keys=True) + "\n").encode())
        await writer.drain()
        raw = await reader.readline()
    finally:
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
    if not raw:
        raise ControlPlaneUnavailable("Control API closed the connection without a response.")
    payload = json.loads(raw.decode())
    if not payload.get("ok"):
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        _fail(f"API error: {error.get('message') or payload}")
    return payload


def _load_valid_config(path: Path | None) -> HerdMasterConfig:
    cfg = load_config(path)
    validate_config(cfg)
    return cfg


def _control_socket_path(cfg: HerdMasterConfig) -> Path:
    api_socket = cfg.paths.socket.expanduser()
    bus_socket = cfg.bus.socket_path.expanduser()
    if api_socket == bus_socket:
        suffix = api_socket.suffix or ".sock"
        return api_socket.with_name(f"{api_socket.stem}-api{suffix}")
    return api_socket


def _bus_config(cfg: HerdMasterConfig) -> Any:
    if cfg.bus.socket_path.expanduser() == _control_socket_path(cfg):
        return replace(cfg.bus, socket_path=cfg.paths.config_dir / "herdmaster-bus.sock")
    return cfg.bus


def _pid_file(cfg: HerdMasterConfig) -> Path:
    return cfg.paths.config_dir / "herdmaster.pid"


def _query(**values: Any) -> JsonDict:
    return {key: value for key, value in values.items() if value is not None}


def _list_data(payload: JsonDict) -> list[JsonDict]:
    data = payload.get("data")
    return [dict(item) for item in data] if isinstance(data, list) else []


def _render_tasks(rows: list[JsonDict], *, title: str = "Tasks") -> None:
    table = Table(title=title)
    for column in ("ID", "Title", "State", "Priority", "Assigned", "Project", "Updated"):
        table.add_column(column)
    for task in rows:
        table.add_row(
            str(task.get("id", "")),
            str(task.get("title", "")),
            str(task.get("state", "")),
            str(task.get("priority", "")),
            str(task.get("assigned_to", "") or ""),
            str(task.get("project_id", "") or ""),
            str(task.get("updated_at", "") or ""),
        )
    console.print(table)


def _render_projects(rows: list[JsonDict], *, title: str = "Projects") -> None:
    table = Table(title=title)
    for column in ("ID", "Name", "State", "Complexity", "ETA Hours", "Progress", "Updated"):
        table.add_column(column)
    for project in rows:
        progress = project.get("progress") if isinstance(project.get("progress"), dict) else {}
        table.add_row(
            str(project.get("id", "")),
            str(project.get("name", "")),
            str(project.get("state", "")),
            str(project.get("complexity_tier", "")),
            str(project.get("eta_expected_hours", "")),
            _progress_text(progress),
            str(project.get("updated_at", "") or ""),
        )
    console.print(table)


def _progress_text(progress: JsonDict) -> str:
    if not progress:
        return ""
    percent = progress.get("percent_complete", progress.get("progress_pct", 0))
    return f"{percent}% ({progress.get('completed', 0)}/{progress.get('total_tasks', 0)})"


def _parse_prometheus_metrics(text: str) -> list[JsonDict]:
    metrics_rows: list[JsonDict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name_labels, _, value = stripped.partition(" ")
        name, labels = _split_metric_labels(name_labels)
        metrics_rows.append({"name": name, "labels": labels, "value": value.strip()})
    return metrics_rows


def _split_metric_labels(value: str) -> tuple[str, str]:
    if "{" not in value:
        return value, ""
    name, labels = value.split("{", 1)
    return name, labels.rstrip("}")


def _seconds_text(value: Any) -> str:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return ""
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours}h {minute}m {sec}s"


def _print_json(value: Any) -> None:
    # Emit plain, parseable JSON. Rich's print_json applies ANSI syntax
    # highlighting which corrupts machine-readable output consumed by `--json`.
    typer.echo(json.dumps(value, default=str, sort_keys=True))


def _print_json_or_message(data: JsonDict, json_output: bool, message: str) -> None:
    if json_output:
        _print_json(data)
    else:
        console.print(message)


def _api_down(exc: Exception) -> None:
    _fail(str(exc), code=2)


def _fail(message: str, *, code: int = 1) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code)

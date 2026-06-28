from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from herdmaster import cli
from herdmaster.db import schema
from herdmaster.db.repositories import AgentRepo, TaskRepo


runner = CliRunner()


class _NoopService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class _AutoStopEvent:
    def __init__(self) -> None:
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True

    async def wait(self) -> bool:
        self._is_set = True
        return True


@pytest.mark.asyncio
async def test_control_plane_seeds_cli_identity_for_task_creator(monkeypatch, test_config):
    async def api_unavailable(_config):
        return False

    async def dispatch_loop(*_args, **_kwargs):
        pass

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_available", api_unavailable)
    monkeypatch.setattr(cli.asyncio, "Event", _AutoStopEvent)
    monkeypatch.setattr(cli, "MessageBusServer", _NoopService)
    monkeypatch.setattr(cli, "WatchdogEngine", _NoopService)
    monkeypatch.setattr(cli, "ControlApiServer", _NoopService)
    monkeypatch.setattr(cli, "_dispatch_loop", dispatch_loop)

    await cli._run_control_plane(None, http_enabled=False)

    conn = schema.connect(test_config.paths.db)
    try:
        assert AgentRepo(conn).get("cli")["role"] == "observer"
        task_id = TaskRepo(conn).create("Created from CLI", "prompt", created_by="cli")
        assert TaskRepo(conn).get(task_id)["created_by"] == "cli"
    finally:
        conn.close()


def test_start_invokes_control_plane_without_real_services(monkeypatch):
    calls = []

    async def run_control_plane(config_path, *, http_enabled):
        calls.append((config_path, http_enabled))

    monkeypatch.setattr(cli, "_run_control_plane", run_control_plane)

    result = runner.invoke(cli.app, ["start", "--http"])

    assert result.exit_code == 0
    assert calls == [(None, True)]


def test_stop_json_checks_status_pid_and_sends_sigterm(monkeypatch, test_config):
    pid_file = test_config.paths.config_dir / "herdmaster.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text("12345", encoding="utf-8")
    killed = []

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(
        cli,
        "_api_call_sync",
        lambda _cfg, method, path, **_kwargs: {
            "ok": True,
            "data": {"state": "running"},
        },
    )
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    result = runner.invoke(cli.app, ["stop", "--json"])

    assert result.exit_code == 0
    assert killed == [(12345, cli.signal.SIGTERM)]
    payload = json.loads(result.stdout)
    assert payload["stopping"] is True
    assert payload["pid"] == 12345
    assert payload["status"] == {"state": "running"}


def test_status_json_uses_control_api_without_socket(monkeypatch, test_config):
    calls = _mock_api(
        monkeypatch,
        test_config,
        {
            ("GET", "/status"): {
                "state": "running",
                "agents": {"total": 2, "unhealthy": 0},
                "tasks": {"queued": 1},
                "projects": {"total": 1},
            }
        },
    )

    result = runner.invoke(cli.app, ["status", "--json"])

    assert result.exit_code == 0
    assert calls == [{"method": "GET", "path": "/status", "body": None, "query": None}]
    assert json.loads(result.stdout)["state"] == "running"


def test_agents_json_lists_known_agents(monkeypatch, test_config):
    calls = _mock_api(
        monkeypatch,
        test_config,
        {
            ("GET", "/agents"): [
                {
                    "id": "w4:pA",
                    "label": "codex",
                    "type": "codex",
                    "role": "worker",
                    "state": "idle",
                    "health": "healthy",
                }
            ]
        },
    )

    result = runner.invoke(cli.app, ["agents", "--json"])

    assert result.exit_code == 0
    assert calls[0]["path"] == "/agents"
    assert json.loads(result.stdout)[0]["id"] == "w4:pA"


def test_metrics_json_parses_prometheus_text(monkeypatch, test_config):
    _mock_api(
        monkeypatch,
        test_config,
        {("GET", "/metrics"): 'herdmaster_agents_total 2\nherdmaster_tasks_total{state="queued"} 3\n'},
    )

    result = runner.invoke(cli.app, ["metrics", "--json"])

    assert result.exit_code == 0
    metrics = json.loads(result.stdout)
    assert metrics == [
        {"labels": "", "name": "herdmaster_agents_total", "value": "2"},
        {"labels": 'state="queued"', "name": "herdmaster_tasks_total", "value": "3"},
    ]


def test_tasks_commands_json_and_cli_seed(monkeypatch, test_config):
    calls = _mock_api(
        monkeypatch,
        test_config,
        {
            ("GET", "/tasks"): [{"id": "T1", "title": "Queued", "state": "queued"}],
            ("POST", "/tasks"): {"id": "T2", "title": "Created", "state": "queued"},
            ("DELETE", "/tasks/T2"): {"id": "T2", "state": "cancelled"},
        },
    )

    listed = runner.invoke(cli.app, ["tasks", "list", "--state", "queued", "--json"])
    created = runner.invoke(cli.app, ["tasks", "create", "Created", "--prompt", "Do it", "--json"])
    cancelled = runner.invoke(cli.app, ["tasks", "cancel", "T2", "--json"])

    assert listed.exit_code == created.exit_code == cancelled.exit_code == 0
    assert json.loads(listed.stdout)[0]["id"] == "T1"
    assert json.loads(created.stdout)["id"] == "T2"
    assert json.loads(cancelled.stdout)["state"] == "cancelled"
    assert calls[0] == {"method": "GET", "path": "/tasks", "body": None, "query": {"state": "queued"}}
    assert calls[1]["body"]["created_by"] == "cli"
    assert calls[1]["body"]["title"] == "Created"
    assert calls[1]["body"]["prompt"] == "Do it"
    assert calls[2]["method"] == "DELETE"


def test_projects_commands_json_and_cli_seed(monkeypatch, test_config):
    calls = _mock_api(
        monkeypatch,
        test_config,
        {
            ("GET", "/projects"): [{"id": "P1", "name": "Existing", "state": "awaiting_approval"}],
            ("POST", "/projects"): {"id": "P2", "name": "Created", "state": "awaiting_approval"},
            ("POST", "/projects/P2/approve"): {
                "project": {"id": "P2", "name": "Created", "state": "in_progress"},
                "task_ids": ["T1"],
            },
        },
    )

    listed = runner.invoke(cli.app, ["projects", "list", "--state", "awaiting_approval", "--json"])
    created = runner.invoke(cli.app, ["projects", "create", "Created", "--scope", "Build it", "--json"])
    approved = runner.invoke(cli.app, ["projects", "approve", "P2", "--notes", "ship", "--json"])

    assert listed.exit_code == created.exit_code == approved.exit_code == 0
    assert json.loads(listed.stdout)[0]["id"] == "P1"
    assert json.loads(created.stdout)["id"] == "P2"
    assert json.loads(approved.stdout)["task_ids"] == ["T1"]
    assert calls[0] == {
        "method": "GET",
        "path": "/projects",
        "body": None,
        "query": {"state": "awaiting_approval"},
    }
    assert calls[1]["body"]["created_by"] == "cli"
    assert calls[1]["body"]["name"] == "Created"
    assert calls[1]["body"]["scope"] == "Build it"
    assert calls[2]["path"] == "/projects/P2/approve"
    assert calls[2]["body"] == {"decision": "accept", "human_notes": "ship"}


def test_config_reload_json_posts_reload_request(monkeypatch, test_config, tmp_path):
    config_path = tmp_path / "config.toml"
    calls = _mock_api(
        monkeypatch,
        test_config,
        {("POST", "/config/reload"): {"reloaded": True, "path": str(config_path)}},
    )

    result = runner.invoke(cli.app, ["config", "reload", "--path", str(config_path), "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": str(config_path), "reloaded": True}
    assert calls == [
        {
            "method": "POST",
            "path": "/config/reload",
            "body": {"path": str(config_path)},
            "query": None,
        }
    ]


def test_control_plane_down_returns_friendly_error(monkeypatch, test_config):
    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)

    def unavailable(*_args, **_kwargs):
        raise cli.ControlPlaneUnavailable("Control plane is not running at /tmp/herdmaster.sock")

    monkeypatch.setattr(cli, "_api_call_sync", unavailable)

    result = runner.invoke(cli.app, ["status", "--json"])

    assert result.exit_code == 2
    assert "Control plane is not running" in result.stdout


def test_control_socket_path_moves_api_when_bus_uses_default_socket(test_config):
    assert cli._control_socket_path(test_config).name == "herdmaster-api.sock"


def _mock_api(monkeypatch, test_config, responses):
    calls = []

    def api_call(_cfg, method, path, *, body=None, query=None):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        key = (method, path)
        if key not in responses:
            raise AssertionError(f"unexpected API call: {key}")
        return {"ok": True, "data": responses[key]}

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_call_sync", api_call)
    return calls

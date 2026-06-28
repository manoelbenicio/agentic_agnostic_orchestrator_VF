"""End-to-end task lifecycle tests via the API dispatch layer (OTTL).

These tests exercise the full task lifecycle — create → list → checkin →
complete / fail — through the same ``ControlApiServer._dispatch`` path used
by the Unix-socket and HTTP transports.  They use the real Postgres-backed
``TaskRepo`` / ``AgentRepo`` (via the ``temp_db`` fixture from conftest.py)
and a real ``TaskQueue``.  No mocks are used for the data layer.

Covered OTTL acceptance criteria:

* ``herdmaster tasks create`` returns a ``task_id`` without error.
* ``herdmaster tasks list`` returns the newly created task.
* ``herdmaster tasks checkin`` sets the task to ``in_progress``.
* ``herdmaster tasks complete`` sets the task to ``done`` with evidence.
* ``herdmaster tasks fail`` sets the task to ``failed`` with reason.
* ``herdmaster tasks ask`` sets the task to ``blocked`` with reason.
* ``herdmaster tasks progress`` updates subtask progress.
* Connection recovery after a failed SQL operation (InFailedTransaction).
* CLI Typer subcommands dispatch correct paths and bodies.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from herdmaster.acl.engine import AclEngine
from herdmaster.api.server import ApiError, ControlApiServer, _Request
from herdmaster.config import AclConfig
from herdmaster.dispatch.injector import DispatchInjector, DispatchInjectorConfig
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.project.planner import ProjectPlanner


class FakeBus:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


def _request(method: str, path: str, *, body=None, query=None) -> _Request:
    return _Request(method, path, query or {}, body or {})


@pytest.fixture
def task_api(repos, mock_herdr_adapter, test_config, tmp_path):
    """Wire a ControlApiServer with real DB repos and queue for task lifecycle tests."""
    queue = TaskQueue(repos.tasks, repos.agents)
    injector = DispatchInjector(
        mock_herdr_adapter,
        queue,
        repos.agents,
        DispatchInjectorConfig(
            idle_timeout_s=1,
            max_chunk_chars=10_000,
            file_fallback_threshold_chars=1_000_000,
            chunk_pace_s=0.0,
            retry_attempts=1,
            base_backoff_s=0.0,
            max_backoff_s=0.0,
            fallback_dir=tmp_path / "prompts",
        ),
    )
    planner = ProjectPlanner(
        repos.projects,
        repos.tasks,
        repos.agents,
        queue,
        injector,
        mock_herdr_adapter,
        test_config,
    )
    bus = FakeBus()
    # Seed the 'cli' agent that the daemon normally creates at startup.
    # The tasks table FK constraint requires created_by to reference agents(id).
    repos.agents.upsert(
        "cli",
        label="CLI Operator",
        agent_type="system",
        role="observer",
        state="idle",
        health="healthy",
        strengths=["cli"],
    )
    server = ControlApiServer(
        config=test_config,
        planner=planner,
        queue=queue,
        agents=repos.agents,
        tasks=repos.tasks,
        projects=repos.projects,
        messages=repos.messages,
        bus=bus,
        acl=AclEngine(test_config.acl),
        socket_path=test_config.paths.socket,
    )
    server._running = True
    return SimpleNamespace(server=server, queue=queue, bus=bus, repos=repos)


# ---------------------------------------------------------------------------
# Task CREATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_create_returns_task_id(task_api, make_agent):
    """AC: herdmaster tasks create retorna task_id sem erro."""
    make_agent("W1", state="idle")

    payload = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={
                "title": "OTTL Test Task",
                "prompt": "Execute OTTL acceptance test",
                "assigned_to": "W1",
                "priority": "high",
                "created_by": "cli",
            },
        )
    )

    assert payload["ok"] is True
    data = payload["data"]
    assert "id" in data
    assert data["title"] == "OTTL Test Task"
    assert data["state"] == "queued"
    assert data["priority"] == 1  # high = 1
    assert data["assigned_to"] == "W1"


@pytest.mark.asyncio
async def test_tasks_create_requires_title_and_prompt(task_api):
    """AC: missing required fields return 400."""
    with pytest.raises(ApiError) as exc_info:
        await task_api.server._dispatch(
            _request("POST", "/tasks", body={"title": "No prompt"})
        )
    assert exc_info.value.status == 400
    assert "prompt" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Task LIST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_list_returns_created_task(task_api, make_agent):
    """AC: tasks list retorna a task criada."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={
                "title": "Listable Task",
                "prompt": "List me",
                "assigned_to": "W1",
                "created_by": "cli",
            },
        )
    )
    task_id = created["data"]["id"]

    listed = await task_api.server._dispatch(
        _request("GET", "/tasks", query={"assigned_to": "W1"})
    )

    assert listed["ok"] is True
    task_ids = [t["id"] for t in listed["data"]]
    assert task_id in task_ids


@pytest.mark.asyncio
async def test_tasks_list_filter_by_state(task_api, make_agent):
    """AC: tasks list --state filters correctly."""
    make_agent("W1", state="idle")

    await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Queued", "prompt": "q", "created_by": "cli"},
        )
    )

    queued = await task_api.server._dispatch(
        _request("GET", "/tasks", query={"state": "queued"})
    )
    done = await task_api.server._dispatch(
        _request("GET", "/tasks", query={"state": "done"})
    )

    assert len(queued["data"]) == 1
    assert len(done["data"]) == 0


# ---------------------------------------------------------------------------
# Task CHECKIN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_checkin_sets_in_progress(task_api, make_agent):
    """AC: herdmaster tasks checkin sucesso — sets state to in_progress."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Checkin Task", "prompt": "Check me in", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    checkin = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/checkin",
            body={"agent_id": "W1"},
        )
    )

    assert checkin["ok"] is True
    assert checkin["data"]["state"] == "in_progress"
    assert checkin["data"]["started_at"] is not None

    # Verify in DB directly
    db_task = task_api.repos.tasks.get(task_id)
    assert db_task["state"] == "in_progress"


@pytest.mark.asyncio
async def test_tasks_checkin_nonexistent_returns_404(task_api):
    """AC: checkin on non-existent task returns 404."""
    with pytest.raises(ApiError) as exc_info:
        await task_api.server._dispatch(
            _request(
                "POST",
                "/tasks/nonexistent-id/checkin",
                body={"agent_id": "W1"},
            )
        )
    assert exc_info.value.status == 404


# ---------------------------------------------------------------------------
# Task COMPLETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_complete_sets_done_with_evidence(task_api, make_agent):
    """AC: herdmaster tasks complete sucesso — sets state to done with evidence."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Complete Task", "prompt": "Complete me", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    # Checkin first
    await task_api.server._dispatch(
        _request("POST", f"/tasks/{task_id}/checkin", body={"agent_id": "W1"})
    )

    # Complete
    completed = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/complete",
            body={"agent_id": "W1", "evidence": "sha256:abc123def456"},
        )
    )

    assert completed["ok"] is True
    assert completed["data"]["state"] == "done"
    assert completed["data"]["completed_by"] == "W1"
    assert completed["data"]["evidence"] == "sha256:abc123def456"
    assert completed["data"]["completed_at"] is not None

    # Verify in DB directly
    db_task = task_api.repos.tasks.get(task_id)
    assert db_task["state"] == "done"
    assert db_task["evidence"] == "sha256:abc123def456"


# ---------------------------------------------------------------------------
# Task FAIL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_fail_sets_failed_with_reason(task_api, make_agent):
    """AC: herdmaster tasks fail sets state to failed with reason."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Fail Task", "prompt": "Fail me", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    failed = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/fail",
            body={"agent_id": "W1", "reason": "compilation error in module X"},
        )
    )

    assert failed["ok"] is True
    assert failed["data"]["state"] == "failed"
    assert failed["data"]["error_message"] == "compilation error in module X"

    db_task = task_api.repos.tasks.get(task_id)
    assert db_task["state"] == "failed"


# ---------------------------------------------------------------------------
# Task ASK (blocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_ask_sets_blocked_with_reason(task_api, make_agent):
    """AC: herdmaster tasks ask blocks a task with a question."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Ask Task", "prompt": "Need help", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    blocked = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/ask",
            body={"reason": "Which database schema should I use?"},
        )
    )

    assert blocked["ok"] is True
    assert blocked["data"]["state"] == "blocked"
    assert blocked["data"]["blocked_reason"] == "Which database schema should I use?"


# ---------------------------------------------------------------------------
# Task PROGRESS (subtask tracking)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_progress_updates_subtask(task_api, make_agent):
    """AC: herdmaster tasks progress updates subtask progress."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={
                "title": "Subtask Task",
                "prompt": "Track subtasks",
                "subtasks": ["design", "implement", "test"],
                "created_by": "cli",
            },
        )
    )
    task_id = created["data"]["id"]

    progress = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/progress",
            body={"subtask": "design", "done": True, "agent_id": "W1"},
        )
    )

    assert progress["ok"] is True
    assert "design" in progress["data"]["progress"]["done"]

    # Mark second subtask
    progress2 = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/progress",
            body={"subtask": "implement", "done": True, "agent_id": "W1"},
        )
    )

    assert set(progress2["data"]["progress"]["done"]) == {"design", "implement"}


# ---------------------------------------------------------------------------
# Task GET by ID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_get_by_id(task_api, make_agent):
    """AC: GET /tasks/{task_id} returns the specific task."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Get Task", "prompt": "Fetch me", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    fetched = await task_api.server._dispatch(
        _request("GET", f"/tasks/{task_id}")
    )

    assert fetched["ok"] is True
    assert fetched["data"]["id"] == task_id
    assert fetched["data"]["title"] == "Get Task"


@pytest.mark.asyncio
async def test_tasks_get_nonexistent_returns_404(task_api):
    """AC: GET /tasks/{bad_id} returns 404."""
    with pytest.raises(ApiError) as exc_info:
        await task_api.server._dispatch(_request("GET", "/tasks/does-not-exist"))
    assert exc_info.value.status == 404


# ---------------------------------------------------------------------------
# Task DELETE (cancel)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tasks_cancel_via_delete(task_api, make_agent):
    """AC: DELETE /tasks/{id} cancels the task."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Cancel Task", "prompt": "Cancel me", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    cancelled = await task_api.server._dispatch(
        _request("DELETE", f"/tasks/{task_id}")
    )

    assert cancelled["ok"] is True
    assert cancelled["data"]["state"] == "cancelled"


# ---------------------------------------------------------------------------
# Full lifecycle: create → list → checkin → complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_task_lifecycle_end_to_end(task_api, make_agent):
    """AC: full lifecycle create → list → checkin → complete all succeed."""
    make_agent("W1", state="idle")

    # 1. CREATE
    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={
                "title": "E2E Lifecycle Task",
                "prompt": "Full lifecycle OTTL test",
                "assigned_to": "W1",
                "priority": "critical",
                "created_by": "cli",
                "subtasks": ["step1", "step2"],
                "acceptance_criteria": ["all tests pass"],
            },
        )
    )
    task_id = created["data"]["id"]
    assert created["data"]["state"] == "queued"
    assert created["data"]["subtasks"] == ["step1", "step2"]

    # 2. LIST — task appears
    listed = await task_api.server._dispatch(
        _request("GET", "/tasks", query={"state": "queued"})
    )
    assert any(t["id"] == task_id for t in listed["data"])

    # 3. CHECKIN — state becomes in_progress
    checkin = await task_api.server._dispatch(
        _request("POST", f"/tasks/{task_id}/checkin", body={"agent_id": "W1"})
    )
    assert checkin["data"]["state"] == "in_progress"

    # 4. PROGRESS — mark subtask done
    progress = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/progress",
            body={"subtask": "step1", "done": True, "agent_id": "W1"},
        )
    )
    assert "step1" in progress["data"]["progress"]["done"]

    # 5. COMPLETE — state becomes done
    completed = await task_api.server._dispatch(
        _request(
            "POST",
            f"/tasks/{task_id}/complete",
            body={"agent_id": "W1", "evidence": "all tests pass: sha256:abcdef"},
        )
    )
    assert completed["data"]["state"] == "done"
    assert completed["data"]["evidence"] == "all tests pass: sha256:abcdef"
    assert completed["data"]["duration_seconds"] is not None

    # Verify final state in DB
    db_task = task_api.repos.tasks.get(task_id)
    assert db_task["state"] == "done"
    assert db_task["completed_by"] == "W1"


# ---------------------------------------------------------------------------
# Connection recovery after InFailedTransaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_recovery_after_failed_transaction(task_api, make_agent):
    """AC: daemon recovers from InFailedTransaction via auto-rollback.

    Simulates a scenario where a SQL error corrupts the transaction state,
    then verifies subsequent operations succeed because PgConnection.execute()
    auto-rolls back.
    """
    make_agent("W1", state="idle")

    # Create a valid task first
    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Recovery Task", "prompt": "Recover", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    # Force a bad SQL to trip the connection into error state.
    # The auto-rollback in PgConnection.execute() should recover it.
    try:
        task_api.repos.tasks.conn.execute("SELECT * FROM nonexistent_table_xyz")
    except Exception:
        pass  # Expected: table doesn't exist

    # After the error, subsequent operations should still work
    # because execute() auto-rolled back the connection.
    fetched = await task_api.server._dispatch(
        _request("GET", f"/tasks/{task_id}")
    )
    assert fetched["ok"] is True
    assert fetched["data"]["id"] == task_id
    assert fetched["data"]["title"] == "Recovery Task"


@pytest.mark.asyncio
async def test_server_recover_connection_clears_state(task_api, make_agent):
    """AC: _recover_connection() rolls back all repos after a failed transaction."""
    make_agent("W1", state="idle")

    # Create a valid task
    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Server Recovery", "prompt": "Recover", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    # Explicitly trigger _recover_connection
    task_api.server._recover_connection()

    # Operations should still work
    listed = await task_api.server._dispatch(
        _request("GET", "/tasks")
    )
    assert listed["ok"] is True
    assert any(t["id"] == task_id for t in listed["data"])


# ---------------------------------------------------------------------------
# CLI Typer subcommands
# ---------------------------------------------------------------------------


def test_cli_tasks_checkin_sends_correct_path(monkeypatch, test_config):
    """AC: CLI tasks checkin subcommand sends POST /tasks/{id}/checkin."""
    from typer.testing import CliRunner
    from herdmaster import cli

    calls = []

    def api_call(_cfg, method, path, *, body=None, query=None):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        return {"ok": True, "data": {"id": "T1", "state": "in_progress", "title": "Test"}}

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_call_sync", api_call)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["tasks", "checkin", "T1", "W1", "--json"])

    assert result.exit_code == 0
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/tasks/T1/checkin"
    assert calls[0]["body"]["agent_id"] == "W1"


def test_cli_tasks_complete_sends_correct_path(monkeypatch, test_config):
    """AC: CLI tasks complete subcommand sends POST /tasks/{id}/complete with evidence."""
    from typer.testing import CliRunner
    from herdmaster import cli

    calls = []

    def api_call(_cfg, method, path, *, body=None, query=None):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        return {"ok": True, "data": {"id": "T1", "state": "done", "title": "Test"}}

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_call_sync", api_call)

    runner = CliRunner()
    result = runner.invoke(
        cli.app, ["tasks", "complete", "T1", "W1", "--evidence", "sha256:abc", "--json"]
    )

    assert result.exit_code == 0
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/tasks/T1/complete"
    assert calls[0]["body"]["agent_id"] == "W1"
    assert calls[0]["body"]["evidence"] == "sha256:abc"


def test_cli_tasks_fail_sends_correct_path(monkeypatch, test_config):
    """AC: CLI tasks fail subcommand sends POST /tasks/{id}/fail with reason."""
    from typer.testing import CliRunner
    from herdmaster import cli

    calls = []

    def api_call(_cfg, method, path, *, body=None, query=None):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        return {"ok": True, "data": {"id": "T1", "state": "failed", "title": "Test"}}

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_call_sync", api_call)

    runner = CliRunner()
    result = runner.invoke(
        cli.app, ["tasks", "fail", "T1", "W1", "--reason", "test failure", "--json"]
    )

    assert result.exit_code == 0
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/tasks/T1/fail"
    assert calls[0]["body"]["agent_id"] == "W1"
    assert calls[0]["body"]["reason"] == "test failure"


def test_cli_tasks_ask_sends_correct_path(monkeypatch, test_config):
    """AC: CLI tasks ask subcommand sends POST /tasks/{id}/ask with reason."""
    from typer.testing import CliRunner
    from herdmaster import cli

    calls = []

    def api_call(_cfg, method, path, *, body=None, query=None):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        return {"ok": True, "data": {"id": "T1", "state": "blocked", "title": "Test"}}

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_call_sync", api_call)

    runner = CliRunner()
    result = runner.invoke(
        cli.app, ["tasks", "ask", "T1", "What schema?", "--json"]
    )

    assert result.exit_code == 0
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/tasks/T1/ask"
    assert calls[0]["body"]["reason"] == "What schema?"


def test_cli_tasks_create_sends_created_by_cli(monkeypatch, test_config):
    """AC: CLI tasks create always includes created_by='cli' in body."""
    from typer.testing import CliRunner
    from herdmaster import cli

    calls = []

    def api_call(_cfg, method, path, *, body=None, query=None):
        calls.append({"method": method, "path": path, "body": body, "query": query})
        return {"ok": True, "data": {"id": "T1", "state": "queued", "title": "Test"}}

    monkeypatch.setattr(cli, "_load_valid_config", lambda _path: test_config)
    monkeypatch.setattr(cli, "_api_call_sync", api_call)

    runner = CliRunner()
    result = runner.invoke(
        cli.app, ["tasks", "create", "My Task", "--prompt", "Do it", "--json"]
    )

    assert result.exit_code == 0
    assert calls[0]["body"]["created_by"] == "cli"
    assert calls[0]["body"]["title"] == "My Task"
    assert calls[0]["body"]["prompt"] == "Do it"


# ---------------------------------------------------------------------------
# Unsupported methods/routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsupported_method_on_tasks_returns_405(task_api):
    """AC: PUT /tasks returns 405."""
    with pytest.raises(ApiError) as exc_info:
        await task_api.server._dispatch(_request("PUT", "/tasks"))
    assert exc_info.value.status == 405


@pytest.mark.asyncio
async def test_unsupported_sub_route_on_tasks_returns_405(task_api, make_agent):
    """AC: POST /tasks/{id}/unknown returns 405."""
    make_agent("W1", state="idle")

    created = await task_api.server._dispatch(
        _request(
            "POST",
            "/tasks",
            body={"title": "Route Task", "prompt": "Test", "created_by": "cli"},
        )
    )
    task_id = created["data"]["id"]

    with pytest.raises(ApiError) as exc_info:
        await task_api.server._dispatch(
            _request("POST", f"/tasks/{task_id}/unknown")
        )
    assert exc_info.value.status == 405

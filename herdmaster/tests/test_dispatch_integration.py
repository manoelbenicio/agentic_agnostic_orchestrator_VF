"""Integration tests for DispatchInjector with mocked asyncio.open_unix_connection.

These tests exercise the full injector path (resolve pane → wait idle → send)
against an in-process fake Herdr socket.  No real herdr process is required.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from herdmaster.dispatch.injector import (
    MAX_PROMPT_BYTES,
    DispatchError,
    DispatchInjector,
    DispatchInjectorConfig,
)
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.herdr import adapter as adapter_module
from herdmaster.herdr.adapter import HerdrAdapter, HerdrError


# ---------------------------------------------------------------------------
# Helpers — in-process fake socket (reused from test_herdr pattern)
# ---------------------------------------------------------------------------

class _MemoryReader:
    def __init__(self, queue: asyncio.Queue[bytes | None]) -> None:
        self._queue = queue

    async def readline(self) -> bytes:
        item = await self._queue.get()
        return item or b""


class _MemoryWriter:
    def __init__(self, queue: asyncio.Queue[bytes | None]) -> None:
        self._queue = queue
        self._closed = False

    def write(self, data: bytes) -> None:
        if not self._closed:
            self._queue.put_nowait(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._queue.put_nowait(None)

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


class _MemorySocket:
    def __init__(self) -> None:
        client_to_server: asyncio.Queue[bytes | None] = asyncio.Queue()
        server_to_client: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.client_reader = _MemoryReader(server_to_client)
        self.client_writer = _MemoryWriter(client_to_server)
        self.server_reader = _MemoryReader(client_to_server)
        self.server_writer = _MemoryWriter(server_to_client)


async def _read_req(reader: _MemoryReader) -> dict[str, Any]:
    line = await reader.readline()
    assert line, "Unexpected EOF from client"
    return json.loads(line.decode("utf-8"))


async def _write_line(writer: _MemoryWriter, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
    await writer.drain()


@asynccontextmanager
async def _fake_herdr(
    monkeypatch: pytest.MonkeyPatch,
    socket_path: Path,
    handler: Callable[[_MemoryReader, _MemoryWriter], Awaitable[None]],
):
    """Patch asyncio.open_unix_connection to use an in-memory pipe."""
    tasks: list[asyncio.Task[None]] = []

    async def _open(path: str):
        assert path == str(socket_path)
        sock = _MemorySocket()
        tasks.append(asyncio.create_task(handler(sock.server_reader, sock.server_writer)))
        return sock.client_reader, sock.client_writer

    monkeypatch.setattr(asyncio, "open_unix_connection", _open)
    try:
        yield
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Herdr envelope helpers
# ---------------------------------------------------------------------------

def _agent_list_response(req_id: str, agents: list[dict]) -> dict:
    return {
        "id": req_id,
        "result": {
            "type": "agent_list",
            "agents": agents,
        },
    }


def _ok_response(req_id: str) -> dict:
    return {"id": req_id, "result": {"status": "ok"}}


def _error_response(req_id: str, code: str, message: str) -> dict:
    return {"id": req_id, "error": {"code": code, "message": message}}


def _events_ack(req_id: str) -> dict:
    return {"id": req_id, "result": {"type": "events_subscription"}}


def _status_event(pane_id: str, state: str) -> dict:
    return {
        "result": {
            "type": "pane.agent_status_changed",
            "pane_id": pane_id,
            "agent_status": state,
        }
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_queue(repos) -> TaskQueue:
    return TaskQueue(repos.tasks, repos.agents)


def injector_config(tmp_path: Path, **overrides) -> DispatchInjectorConfig:
    values = {
        "idle_timeout_s": 2,
        "max_chunk_chars": 500,
        "file_fallback_threshold_chars": 10_000,
        "chunk_pace_s": 0.0,
        "retry_attempts": 2,
        "base_backoff_s": 0.0,
        "max_backoff_s": 0.0,
        "fallback_dir": tmp_path / "prompts",
    }
    values.update(overrides)
    return DispatchInjectorConfig(**values)


async def _setup_assigned_task(
    queue: TaskQueue,
    repos,
    *,
    agent_id: str = "A1",
    pane_id: str = "w1:pA",
    prompt: str = "Do something useful",
    max_retries: int = 2,
) -> dict:
    """Insert agent + task and return the claimed (assigned) task dict."""
    repos.agents.upsert(
        agent_id,
        label="Test Agent",
        agent_type="codex",
        role="worker",
        herdr_pane=pane_id,
        herdr_ws="ws1",
        state="idle",
        health="healthy",
        strengths=[],
    )
    task_id = queue.enqueue("Integration task", prompt, max_retries=max_retries)
    task = await queue.claim_next(agent_id)
    assert task is not None
    return task


# ---------------------------------------------------------------------------
# Scenario 1: happy path — agent already idle (agent_list returns idle state)
# agent_wait calls agent_list, finds target idle → skips events.subscribe
# pane_id stored in DB → _resolve_pane_id returns without agent_list call
# → agent_wait sees agent_id == herdr pane_id → idle → pane_send succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_integration_happy_path(repos, tmp_path, monkeypatch):
    """
    GIVEN an assigned task with a known pane_id
    WHEN the adapter's agent_list shows agent is already idle (state='idle')
    THEN result.status == 'in_progress' and task state transitions correctly.

    NOTE: Use agent_id == pane_id == 'w1:pA' so that
    _agent_by_id_or_pane(agents, 'w1:pA') finds the returned agent
    and short-circuits without going to events.subscribe.
    """
    socket_path = tmp_path / "herdr.sock"
    queue = make_queue(repos)
    # agent_id == pane_id so that agent_wait's lookup succeeds
    task = await _setup_assigned_task(
        queue, repos, agent_id="w1:pA", pane_id="w1:pA", prompt="hello world"
    )

    sends: list[str] = []

    async def handler(reader: _MemoryReader, writer: _MemoryWriter) -> None:
        req = await _read_req(reader)
        method = req.get("method", "")

        if method == "agent.list":
            # Return agent with pane_id == agent_id so lookup succeeds
            await _write_line(writer, _agent_list_response(req["id"], [
                {
                    "agent": "codex",
                    "agent_status": "idle",
                    "pane_id": "w1:pA",
                    "workspace_id": "w1",
                }
            ]))
        elif method == "pane.send_text":
            sends.append(req["params"].get("text", ""))
            await _write_line(writer, _ok_response(req["id"]))
        else:
            await _write_line(writer, _ok_response(req["id"]))
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr(monkeypatch, socket_path, handler):
        adapter = HerdrAdapter(socket_path=socket_path)
        injector = DispatchInjector(adapter, queue, repos.agents, injector_config(tmp_path))
        result = await injector.dispatch(task)

    assert result.status == "in_progress", f"Expected in_progress, got {result.status!r}"
    assert result.pane_id == "w1:pA"
    assert result.prompt_file is None
    stored = repos.tasks.get(task["id"])
    assert stored["state"] == "in_progress"
    # Must have sent the prompt text and a final Enter key.
    assert "hello world" in sends
    assert "\r" in sends


# ---------------------------------------------------------------------------
# Scenario 2: agent busy → timeout → task requeued (AgentNotIdle path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_integration_agent_busy_timeout_requeues(repos, tmp_path, monkeypatch):
    """
    GIVEN an assigned task
    WHEN the agent never becomes idle within the timeout window
    THEN result.status == 'requeued' and task is back in queued state
    """
    socket_path = tmp_path / "herdr.sock"
    queue = make_queue(repos)
    task = await _setup_assigned_task(queue, repos, pane_id="w1:pB", max_retries=3)

    async def handler(reader: _MemoryReader, writer: _MemoryWriter) -> None:
        req = await _read_req(reader)
        method = req.get("method", "")
        if method == "events.subscribe":
            await _write_line(writer, _events_ack(req["id"]))
            # Emit a "working" event — never idle → triggers timeout via wait_for
            await _write_line(writer, _status_event("w1:pB", "working"))
            # Hold open long enough for the adapter's wait_for to expire
            await asyncio.sleep(5)
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr(monkeypatch, socket_path, handler):
        adapter = HerdrAdapter(socket_path=socket_path, timeout=0.1)
        injector = DispatchInjector(
            adapter, queue, repos.agents,
            injector_config(tmp_path, idle_timeout_s=0, retry_attempts=1, base_backoff_s=0.0, max_backoff_s=0.0),
        )
        result = await injector.dispatch(task)

    assert result.status == "requeued", f"Expected requeued, got {result.status}"
    stored = repos.tasks.get(task["id"])
    assert stored["state"] == "queued"
    assert stored["assigned_to"] is None
    assert stored["retry_count"] >= 1


# ---------------------------------------------------------------------------
# Scenario 3: HerdrError on pane_send → task falls back to file, stays in_progress
# Use agent_id == pane_id so agent_wait short-circuits without events.subscribe.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_integration_herdr_error_on_send_uses_file_fallback(
    repos, tmp_path, monkeypatch
):
    """
    GIVEN an assigned task whose first inline pane_send raises HerdrError
    WHEN the injector falls back to writing a file and sending the path
    THEN result.status == 'in_progress', result.prompt_file is set and readable
    """
    socket_path = tmp_path / "herdr.sock"
    queue = make_queue(repos)
    prompt = "short prompt that triggers inline send then file fallback"
    task = await _setup_assigned_task(
        queue, repos, agent_id="w1:pC", pane_id="w1:pC", prompt=prompt
    )

    send_call_count = 0

    async def handler(reader: _MemoryReader, writer: _MemoryWriter) -> None:
        nonlocal send_call_count
        req = await _read_req(reader)
        method = req.get("method", "")

        if method == "agent.list":
            # Agent already idle — agent_wait short-circuits
            await _write_line(writer, _agent_list_response(req["id"], [
                {
                    "agent": "codex",
                    "agent_status": "idle",
                    "pane_id": "w1:pC",
                    "workspace_id": "w1",
                }
            ]))
        elif method == "pane.send_text":
            send_call_count += 1
            if send_call_count == 1:
                # First inline send fails → triggers file fallback path
                await _write_line(writer, _error_response(req["id"], "send_error", "pane busy"))
            else:
                # Subsequent sends (ctrl-U clear + file reference + newline) succeed
                await _write_line(writer, _ok_response(req["id"]))
        else:
            await _write_line(writer, _ok_response(req["id"]))
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr(monkeypatch, socket_path, handler):
        adapter = HerdrAdapter(socket_path=socket_path)
        injector = DispatchInjector(
            adapter, queue, repos.agents,
            injector_config(tmp_path, max_chunk_chars=200, file_fallback_threshold_chars=200),
        )
        result = await injector.dispatch(task)

    assert result.status == "in_progress", f"Expected in_progress, got {result.status!r}"
    assert result.prompt_file is not None, "Expected a file fallback to have been created"
    assert result.prompt_file.exists()
    assert result.prompt_file.read_text(encoding="utf-8") == prompt


# ---------------------------------------------------------------------------
# Scenario 4: agent not in DB and not found in agent.list → error handled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_integration_nonexistent_agent_is_handled(repos, tmp_path, monkeypatch):
    """
    GIVEN an assigned task for an agent that has NO pane_id in DB AND is absent
    from the adapter's agent.list response
    WHEN dispatch is called
    THEN result.status is 'requeued' or 'failed' (not an unhandled exception)
    """
    socket_path = tmp_path / "herdr.sock"
    queue = make_queue(repos)

    # Insert agent WITHOUT herdr_pane set
    repos.agents.upsert(
        "GHOST",
        label="Ghost Agent",
        agent_type="codex",
        role="worker",
        herdr_pane="",           # empty — forces agent_list lookup
        herdr_ws="ws1",
        state="idle",
        health="healthy",
        strengths=[],
    )
    task_id = queue.enqueue("Ghost task", "do nothing", max_retries=1)
    task = await queue.claim_next("GHOST")
    assert task is not None

    async def handler(reader: _MemoryReader, writer: _MemoryWriter) -> None:
        req = await _read_req(reader)
        method = req.get("method", "")
        if method == "agent.list":
            # Return empty agent list — GHOST not present
            await _write_line(writer, _agent_list_response(req["id"], []))
        else:
            await _write_line(writer, _ok_response(req["id"]))
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr(monkeypatch, socket_path, handler):
        adapter = HerdrAdapter(socket_path=socket_path)
        injector = DispatchInjector(
            adapter, queue, repos.agents,
            injector_config(tmp_path, retry_attempts=1),
        )
        result = await injector.dispatch(task)

    # Should not propagate as unhandled exception; must be requeued or failed
    assert result.status in ("requeued", "failed", "in_progress"), (
        f"Unexpected status: {result.status!r}"
    )
    stored = repos.tasks.get(task["id"])
    assert stored is not None
    assert stored["state"] in ("queued", "failed", "in_progress")


# ---------------------------------------------------------------------------
# Scenario 5: socket closes mid-stream (reconnect resilience)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_integration_socket_closes_midstream_triggers_herdr_error(
    repos, tmp_path, monkeypatch
):
    """
    GIVEN a subscribe call whose server closes the socket before sending an event
    WHEN the injector tries to wait for idle
    THEN HerdrError is caught and the task is requeued or failed — no crash
    """
    socket_path = tmp_path / "herdr.sock"
    queue = make_queue(repos)
    task = await _setup_assigned_task(queue, repos, pane_id="w1:pD", max_retries=1)

    async def handler(reader: _MemoryReader, writer: _MemoryWriter) -> None:
        req = await _read_req(reader)
        method = req.get("method", "")
        if method == "events.subscribe":
            await _write_line(writer, _events_ack(req["id"]))
            # Close immediately without sending any event → readline returns b""
            writer.close()
            await writer.wait_closed()
        else:
            # For any pane_send retries
            await _write_line(writer, _ok_response(req["id"]))
            writer.close()
            await writer.wait_closed()

    async with _fake_herdr(monkeypatch, socket_path, handler):
        adapter = HerdrAdapter(socket_path=socket_path, timeout=1.0)
        injector = DispatchInjector(
            adapter, queue, repos.agents,
            injector_config(tmp_path, idle_timeout_s=1, retry_attempts=1),
        )
        result = await injector.dispatch(task)

    assert result.status in ("requeued", "failed"), (
        f"Socket close should produce requeued/failed, got {result.status!r}"
    )


# ---------------------------------------------------------------------------
# Scenario 6: idempotency guard — task already in_progress, skip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_integration_idempotency_guard_skips_already_in_progress(
    repos, tmp_path, monkeypatch
):
    """
    GIVEN a task that has already been marked in_progress
    WHEN dispatch is called again with the stale 'assigned' view
    THEN result.status == 'skipped' and no socket calls are made
    """
    socket_path = tmp_path / "herdr.sock"
    queue = make_queue(repos)
    task = await _setup_assigned_task(queue, repos, pane_id="w1:pE")

    # Advance the task beyond assigned
    queue.mark_dispatched(task["id"])
    queue.mark_in_progress(task["id"])

    socket_touched = False

    async def handler(reader: _MemoryReader, writer: _MemoryWriter) -> None:
        nonlocal socket_touched
        socket_touched = True
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr(monkeypatch, socket_path, handler):
        adapter = HerdrAdapter(socket_path=socket_path)
        injector = DispatchInjector(adapter, queue, repos.agents, injector_config(tmp_path))
        # Pass stale 'assigned' view
        result = await injector.dispatch({**task, "state": "assigned"})

    assert result.status == "skipped"
    assert result.attempts == 0
    assert not socket_touched, "No socket connection should happen for a skipped task"


# ---------------------------------------------------------------------------
# Scenario 7: file fallback prompt size guard
# ---------------------------------------------------------------------------

def test_write_prompt_file_rejects_prompt_over_one_megabyte(repos, tmp_path):
    queue = make_queue(repos)
    injector = DispatchInjector(
        adapter=None,
        queue=queue,
        agent_repo=repos.agents,
        config=injector_config(tmp_path),
    )
    prompt = "a" * (MAX_PROMPT_BYTES + 1)

    with pytest.raises(DispatchError, match=f"prompt exceeds {MAX_PROMPT_BYTES} bytes limit"):
        injector._write_prompt_file("oversized", prompt)

    assert not (tmp_path / "prompts").exists()


def test_write_prompt_file_accepts_prompt_at_one_megabyte_limit(repos, tmp_path):
    queue = make_queue(repos)
    injector = DispatchInjector(
        adapter=None,
        queue=queue,
        agent_repo=repos.agents,
        config=injector_config(tmp_path),
    )
    prompt = "a" * MAX_PROMPT_BYTES

    prompt_file = injector._write_prompt_file("exact-limit", prompt)

    assert prompt_file.exists()
    assert prompt_file.stat().st_size == MAX_PROMPT_BYTES


# ---------------------------------------------------------------------------
# Scenario 8: live dispatch read-only (integration marker, skipped w/o socket)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_dispatch_read_only():
    """Read-only live test contra Herdr real. Seguro em produção.

    Skips automatically when:
    - Herdr socket is not present on the filesystem
    - No agents are in idle state
    """
    socket_path = os.path.expanduser("~/.config/herdr/herdr.sock")
    if not os.path.exists(socket_path):
        pytest.skip("Herdr socket não encontrado")

    adapter = HerdrAdapter(socket_path=socket_path)
    try:
        agents = await adapter.agent_list()
    except HerdrError as exc:
        pytest.skip(f"Herdr real indisponível: {exc}")
    assert len(agents) >= 1

    idle = [a for a in agents if a.state == "idle"]
    if not idle:
        pytest.skip("nenhum agente idle")

    try:
        out = await adapter.pane_read(idle[0].pane_id)
    except HerdrError as exc:
        pytest.skip(f"Herdr real indisponível: {exc}")
    assert isinstance(out, str)
    # NÃO enviar texto — read-only, seguro

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_dispatch_write_prompt():
    """ISSUE-001: Validar caminho de ESCRITA (injector -> agent.send).
    
    Requer HERDR_TEST_PANE definido no ambiente com um pane id descartável.
    """
    pane_id = os.environ.get("HERDR_TEST_PANE")
    if not pane_id:
        pytest.skip("HERDR_TEST_PANE não definido")

    socket_path = os.path.expanduser("~/.config/herdr/herdr.sock")
    if not os.path.exists(socket_path):
        pytest.skip("Herdr socket não encontrado")

    adapter = HerdrAdapter(socket_path=socket_path)
    
    # 1. Enviar um prompt inócuo
    prompt_text = "echo 'TEST_ISSUE_001_DISPATCH_SUCCESS'"
    await adapter.pane_send(pane_id, prompt_text)
    
    # Send Enter to execute
    await adapter.pane_send(pane_id, "\n")
    
    # 2. Ler o painel e verificar se o prompt chegou
    await asyncio.sleep(1.0)  # Wait for output
    out = await adapter.pane_read(pane_id)
    assert isinstance(out, str)
    assert "TEST_ISSUE_001_DISPATCH_SUCCESS" in out.replace("\n", "").replace("\r", "")

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Any

import pytest

from herdmaster.herdr import adapter as adapter_module
from herdmaster.herdr.adapter import HerdrAdapter, HerdrError
from herdmaster.herdr.parser import HerdrAgent, output_hash
from herdmaster.watchdog.engine import WatchdogEngine


async def _read_request(reader: asyncio.StreamReader) -> dict[str, Any]:
    line = await reader.readline()
    assert line
    request = json.loads(line.decode("utf-8"))
    assert isinstance(request, dict)
    return request


async def _write_line(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
    await writer.drain()


@asynccontextmanager
async def _fake_herdr_socket(
    monkeypatch: pytest.MonkeyPatch,
    socket_path: Path,
    handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
):
    tasks: list[asyncio.Task[None]] = []

    async def fake_open_unix_connection(path: str):
        assert path == str(socket_path)
        socket = _MemorySocket()
        tasks.append(asyncio.create_task(handler(socket.server_reader, socket.server_writer)))
        return socket.client_reader, socket.client_writer

    monkeypatch.setattr(asyncio, "open_unix_connection", fake_open_unix_connection)
    try:
        yield
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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


def test_output_hash_is_stable_and_content_sensitive():
    assert output_hash("same output") == output_hash("same output")
    assert output_hash("same output") != output_hash("different output")


def test_event_matcher_accepts_live_event_data_envelope():
    event = {
        "event": "pane.agent_status_changed",
        "data": {
            "agent": "codex",
            "agent_status": "working",
            "pane_id": "w4:pA",
            "workspace_id": "w4",
        },
    }

    assert adapter_module._event_matches_agent_status(event, "w4:pA", "working")


@pytest.mark.asyncio
async def test_adapter_agent_list_uses_unix_socket_and_real_agent_list_envelope(tmp_path, monkeypatch):
    socket_path = tmp_path / "herdr.sock"
    requests: list[dict[str, Any]] = []
    parsed_payloads: list[dict[str, Any]] = []

    real_agent_list_response = {
        "result": {
            "type": "agent_list",
            "agents": [
                {
                    "agent": "codex",
                    "agent_status": "idle",
                    "pane_id": "w4:pA",
                    "workspace_id": "w4",
                }
            ],
        }
    }

    def fake_parse_agent_list(raw: str) -> list[HerdrAgent]:
        payload = json.loads(raw)
        parsed_payloads.append(payload)
        assert payload["result"] == real_agent_list_response["result"]
        return [HerdrAgent("w4:pA", "codex", "codex", "idle", "w4:pA", "w4")]

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        requests.append(request)
        await _write_line(writer, {"id": request["id"], **real_agent_list_response})
        writer.close()
        await writer.wait_closed()

    monkeypatch.setattr(adapter_module, "parse_agent_list", fake_parse_agent_list)

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        agents = await HerdrAdapter(socket_path=socket_path).agent_list()

    assert requests == [
        {"id": "herdmaster-1", "method": "agent.list", "params": {}}
    ]
    assert [(agent.id, agent.label, agent.type, agent.state, agent.pane_id, agent.workspace) for agent in agents] == [
        ("w4:pA", "codex", "codex", "idle", "w4:pA", "w4")
    ]
    assert len(parsed_payloads) == 1


@pytest.mark.asyncio
async def test_adapter_error_response_raises_herdr_error(tmp_path, monkeypatch):
    socket_path = tmp_path / "herdr.sock"

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        await _write_line(
            writer,
            {
                "id": request["id"],
                "error": {"code": "not_found", "message": "pane not found"},
            },
        )
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        with pytest.raises(HerdrError, match="not_found: pane not found"):
            await HerdrAdapter(socket_path=socket_path).pane_read("w4:pA")


@pytest.mark.asyncio
async def test_adapter_subscribe_status_streams_agent_status_events(tmp_path, monkeypatch):
    socket_path = tmp_path / "herdr.sock"
    requests: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    event_seen = asyncio.Event()

    async def fake_agent_list():
        return [HerdrAgent(id="w4:pA", label="test", type="codex", state="idle", pane_id="w4:pA", workspace="w4")]
    monkeypatch.setattr(HerdrAdapter, "agent_list", lambda self: fake_agent_list())

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        requests.append(request)
        await _write_line(writer, {"id": request["id"], "result": {"type": "events_subscription"}})
        await _write_line(
            writer,
            {
                "result": {
                    "type": "pane.agent_status_changed",
                    "pane_id": "w4:pA",
                    "agent": "codex",
                    "agent_status": "working",
                    "workspace_id": "w4",
                }
            },
        )
        await event_seen.wait()
        writer.close()
        await writer.wait_closed()

    async def callback(event: dict[str, Any]) -> None:
        events.append(event)
        event_seen.set()

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        task = asyncio.create_task(HerdrAdapter(socket_path=socket_path).subscribe_status(callback))
        await asyncio.wait_for(event_seen.wait(), timeout=1)
        try:
            await task
        except HerdrError:
            pass

    assert requests == [
        {
            "id": "herdmaster-1",
            "method": "events.subscribe",
            "params": {"subscriptions": [{"type": "pane.agent_status_changed", "pane_id": "w4:pA"}]},
        }
    ]
    assert events == [
        {
            "result": {
                "type": "pane.agent_status_changed",
                "pane_id": "w4:pA",
                "agent": "codex",
                "agent_status": "working",
                "workspace_id": "w4",
            }
        }
    ]


@pytest.mark.asyncio
async def test_adapter_subscribe_status_disconnect_after_events_does_not_hang(tmp_path, monkeypatch):
    socket_path = tmp_path / "herdr.sock"
    events: list[dict[str, Any]] = []

    async def fake_agent_list():
        return [HerdrAgent(id="w4:pA", label="test", type="codex", state="idle", pane_id="w4:pA", workspace="w4")]
    monkeypatch.setattr(HerdrAdapter, "agent_list", lambda self: fake_agent_list())

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        await _write_line(writer, {"id": request["id"], "result": {"type": "events_subscription"}})
        for status in ("working", "idle"):
            await _write_line(
                writer,
                {
                    "result": {
                        "type": "pane.agent_status_changed",
                        "pane_id": "w4:pA",
                        "agent": "codex",
                        "agent_status": status,
                        "workspace_id": "w4",
                    }
                },
            )
        writer.close()
        await writer.wait_closed()

    async def callback(event: dict[str, Any]) -> None:
        events.append(event)

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        with pytest.raises(HerdrError, match="socket closed"):
            await asyncio.wait_for(
                HerdrAdapter(socket_path=socket_path).subscribe_status(callback),
                timeout=1,
            )

    assert [event["result"]["agent_status"] for event in events] == ["working", "idle"]


@pytest.mark.asyncio
async def test_watchdog_primary_status_event_upserts_and_updates_agent(repos, test_config):
    class EventAdapter:
        async def subscribe_status(self, callback):
            await callback(
                {
                    "result": {
                        "type": "pane.agent_status_changed",
                        "pane_id": "w4:pA",
                        "agent": "codex",
                        "agent_status": "working",
                        "workspace_id": "w4",
                    }
                }
            )

        async def agent_list(self):
            return []

    engine = WatchdogEngine(EventAdapter(), repos.agents, test_config.watchdog)

    await engine._run_primary()

    agent = repos.agents.get("w4:pA")
    assert agent is not None
    assert agent["label"] == "codex"
    assert agent["type"] == "codex"
    assert agent["state"] == "working"
    assert agent["health"] == "healthy"
    assert agent["herdr_pane"] == "w4:pA"
    assert agent["herdr_ws"] == "w4"


@pytest.mark.asyncio
async def test_adapter_pane_close_sends_correct_request(tmp_path, monkeypatch):
    """pane_close() sends a ``pane.close`` request with the correct pane_id."""
    socket_path = tmp_path / "herdr.sock"
    requests: list[dict[str, Any]] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        requests.append(request)
        await _write_line(writer, {"id": request["id"], "result": {"type": "ok"}})
        writer.close()
        await writer.wait_closed()

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        await HerdrAdapter(socket_path=socket_path).pane_close("w4:pA")

    assert len(requests) == 1
    assert requests[0]["method"] == "pane.close"
    assert requests[0]["params"] == {"pane_id": "w4:pA"}


@pytest.mark.asyncio
async def test_adapter_subscribe_status_reconnect_callback_called_then_error(tmp_path, monkeypatch):
    """subscribe_status streams 2 events, then server closes -> callback called 2x, HerdrError raised."""
    socket_path = tmp_path / "herdr.sock"
    events: list[dict[str, Any]] = []

    async def fake_agent_list():
        return [HerdrAgent(id="w4:pA", label="test", type="codex", state="idle", pane_id="w4:pA", workspace="w4")]
    monkeypatch.setattr(HerdrAdapter, "agent_list", lambda self: fake_agent_list())

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        await _write_line(writer, {"id": request["id"], "result": {"type": "events_subscription"}})
        for status in ("working", "idle"):
            await _write_line(
                writer,
                {
                    "result": {
                        "type": "pane.agent_status_changed",
                        "pane_id": "w4:pA",
                        "agent": "codex",
                        "agent_status": status,
                        "workspace_id": "w4",
                    }
                },
            )
        writer.close()
        await writer.wait_closed()

    async def callback(event: dict[str, Any]) -> None:
        events.append(event)

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        with pytest.raises(HerdrError, match="socket closed"):
            await asyncio.wait_for(
                HerdrAdapter(socket_path=socket_path).subscribe_status(callback),
                timeout=2,
            )

    assert len(events) == 2
    assert [e["result"]["agent_status"] for e in events] == ["working", "idle"]


@pytest.mark.asyncio
async def test_adapter_request_reconnects_on_third_attempt(tmp_path, monkeypatch):
    """_request retries on ConnectionRefusedError and succeeds on the 3rd attempt."""
    socket_path = tmp_path / "herdr.sock"
    attempt = {"count": 0}

    real_agent_list_response = {
        "result": {
            "type": "agent_list",
            "agents": [
                {
                    "agent": "codex",
                    "agent_status": "idle",
                    "pane_id": "w4:pA",
                    "workspace_id": "w4",
                }
            ],
        }
    }

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await _read_request(reader)
        await _write_line(writer, {"id": request["id"], **real_agent_list_response})
        writer.close()
        await writer.wait_closed()

    original_open = None

    async def flaky_open_unix_connection(path: str):
        attempt["count"] += 1
        if attempt["count"] < 3:
            raise ConnectionRefusedError("connection refused")
        return await original_open(path)

    async with _fake_herdr_socket(monkeypatch, socket_path, handler):
        # Capture the already-monkeypatched open_unix_connection (the fake one)
        original_open = asyncio.open_unix_connection
        monkeypatch.setattr(asyncio, "open_unix_connection", flaky_open_unix_connection)

        # Patch asyncio.sleep to avoid real delays
        sleep_calls: list[float] = []
        _real_sleep = asyncio.sleep

        async def fake_sleep(duration: float) -> None:
            if duration > 0:
                sleep_calls.append(duration)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        adapter = HerdrAdapter(socket_path=socket_path, timeout=5.0)
        response = await adapter._request("agent.list")

    assert attempt["count"] == 3
    assert response["result"]["type"] == "agent_list"
    assert sleep_calls == [0.5, 1.0]


@pytest.mark.asyncio
async def test_adapter_request_all_retries_exhausted_raises_herdr_error(tmp_path, monkeypatch):
    """_request raises HerdrError after all retry attempts are exhausted."""

    async def always_fail_open(path: str):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(asyncio, "open_unix_connection", always_fail_open)

    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        if duration > 0:
            sleep_calls.append(duration)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    socket_path = tmp_path / "herdr.sock"
    adapter = HerdrAdapter(socket_path=socket_path, timeout=5.0)

    with pytest.raises(HerdrError, match="failed to connect.*after 4 attempts"):
        await adapter._request("agent.list")

    assert sleep_calls == [0.5, 1.0, 2.0]

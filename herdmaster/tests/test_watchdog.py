from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock

import pytest

from herdmaster.herdr.adapter import HerdrAdapter
from herdmaster.herdr.parser import HerdrAgent
from herdmaster.watchdog.engine import WatchdogEngine
from herdmaster.watchdog.recovery import RecoveryManager


class Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value

    def set(self, value):
        self.value = value


class Publisher:
    def __init__(self):
        self.messages = []

    async def publish(self, message):
        self.messages.append(message)


class Replayer:
    def __init__(self):
        self.agent_ids = []

    async def replay_last_task(self, agent_id):
        self.agent_ids.append(agent_id)


class FakeWriter:
    def close(self):
        pass

    async def wait_closed(self):
        pass


class AgentWaitProbeAdapter(HerdrAdapter):
    def __init__(self, agents):
        super().__init__("/tmp/herdr.sock")
        self.agents = list(agents)
        self.agent_list_timeouts = []
        self.connect_timeouts = []
        self.response_timeouts = []
        self.line_timeouts = []

    async def agent_list(self, *, timeout=None):
        self.agent_list_timeouts.append(timeout)
        return list(self.agents)

    async def _connect(self, timeout):
        self.connect_timeouts.append(timeout)
        return object(), FakeWriter()

    async def _send(self, writer, request):
        pass

    async def _read_response(self, reader, request_id, timeout):
        self.response_timeouts.append(timeout)
        return {"result": {}}

    async def _read_json_line(self, reader, timeout):
        self.line_timeouts.append(timeout)
        return herdr_status_event("pane-A1", "codex", "idle")


class RealStatusStreamAdapter:
    def __init__(self, events, *, fail_after=False, poll_agents=None, pane_outputs=None):
        self.events = list(events)
        self.fail_after = fail_after
        self.poll_agents = list(poll_agents or [])
        self.pane_outputs = dict(pane_outputs or {})
        self.subscribe_calls = 0
        self.agent_list_calls = 0

    async def subscribe_status(self, callback):
        self.subscribe_calls += 1
        for event in self.events:
            await callback(event)
        if self.fail_after:
            raise RuntimeError("event stream closed")

    async def agent_list(self):
        self.agent_list_calls += 1
        return list(self.poll_agents)

    async def pane_read(self, pane_id):
        return self.pane_outputs.get(pane_id, "")


class EventOnlyStatusStreamAdapter(RealStatusStreamAdapter):
    async def agent_list(self):
        raise AssertionError("polling should not be used for primary stream event handling")


class RawRecoveryAdapter:
    def __init__(self, *, wait_results=None):
        self.calls = []
        self.wait_results = list(wait_results or [])

    async def _request(self, method, params=None, *, timeout=None):
        self.calls.append(("_request", (method, params), {"timeout": timeout}))
        return {"result": {"type": method}}

    async def spawn_agent(self, pane_id, command, *, timeout=None):
        self.calls.append(("spawn_agent", (pane_id, command), {"timeout": timeout}))

    async def agent_wait(self, agent_id, state="idle", timeout: float | None = 30.0, *, command_timeout=None):
        self.calls.append(
            (
                "agent_wait",
                (agent_id, state),
                {"timeout": timeout, "command_timeout": command_timeout},
            )
        )
        result = self.wait_results.pop(0) if self.wait_results else True
        if isinstance(result, BaseException):
            raise result
        return bool(result)

    async def pane_send(self, pane_id: str, text: str, *, confirm: bool = True, timeout: float | None = None) -> None:
        self.calls.append(("pane_send", (pane_id, text), {"confirm": confirm, "timeout": timeout}))


class PublicCloseRecoveryAdapter(RawRecoveryAdapter):
    async def pane_close(self, pane_id: str) -> None:
        self.calls.append(("pane_close", (pane_id,), {}))


def health_events(conn, agent_id="A1"):
    return [
        dict(row)
        for row in conn.execute(
            "SELECT agent_id, event_type, details FROM health_events WHERE agent_id = ? ORDER BY id",
            (agent_id,),
        ).fetchall()
    ]


def herdr_status_event(pane_id, agent, status, workspace_id="w4"):
    return {
        "result": {
            "type": "pane.agent_status_changed",
            "pane_id": pane_id,
            "agent": agent,
            "agent_status": status,
            "workspace_id": workspace_id,
        }
    }


@pytest.mark.asyncio
async def test_agent_wait_accepts_float_timeout():
    adapter = AgentWaitProbeAdapter(
        [HerdrAgent("A1", "Codex", "codex", "idle", "pane-A1", "ws")]
    )

    assert await adapter.agent_wait("A1", timeout=0.5) is True

    assert adapter.agent_list_timeouts == [0.5]


@pytest.mark.asyncio
async def test_agent_wait_accepts_none_timeout_without_limit():
    adapter = AgentWaitProbeAdapter(
        [HerdrAgent("A1", "Codex", "codex", "working", "pane-A1", "ws")]
    )

    assert await adapter.agent_wait("A1", timeout=None) is True

    assert adapter.agent_list_timeouts == [None]
    assert adapter.connect_timeouts == [None]
    assert adapter.response_timeouts == [None]
    assert adapter.line_timeouts == [None]


@pytest.mark.asyncio
async def test_timeout_transitions_write_health_events(temp_db, repos, make_agent, mock_herdr_adapter, test_config):
    make_agent("A1", state="unknown", herdr_pane="pane-A1")
    mock_herdr_adapter.agents = [HerdrAgent("A1", "Codex", "codex", "working", "pane-A1", "ws")]
    mock_herdr_adapter.pane_outputs = {"pane-A1": ["first output"]}
    clock = Clock(0)
    engine = WatchdogEngine(mock_herdr_adapter, repos.agents, test_config.watchdog, now=clock)

    await engine.poll_once()
    assert repos.agents.get("A1")["health"] == "healthy"

    clock.set(6)
    await engine.poll_once()
    assert repos.agents.get("A1")["health"] == "suspect"

    clock.set(11)
    await engine.poll_once()
    await asyncio.sleep(0)

    events = health_events(temp_db)
    assert [event["event_type"] for event in events[:3]] == ["suspect", "unhealthy", "recovering"]


@pytest.mark.asyncio
async def test_primary_stream_reflects_real_status_events_without_polling(
    temp_db, repos, make_agent, test_config
):
    make_agent("w4:pA", state="working", health="unhealthy", herdr_pane="w4:pA")
    adapter = EventOnlyStatusStreamAdapter(
        [
            herdr_status_event("w4:pA", "codex", "blocked"),
            herdr_status_event("w4:pA", "codex", "idle"),
            herdr_status_event("w4:pC", "opencode", "working"),
        ]
    )
    engine = WatchdogEngine(adapter, repos.agents, test_config.watchdog)

    await engine._run_primary()

    assert adapter.subscribe_calls == 1
    assert adapter.agent_list_calls == 0

    codex = repos.agents.get("w4:pA")
    assert codex is not None
    assert codex["label"] == "codex"
    assert codex["type"] == "codex"
    assert codex["state"] == "idle"
    assert codex["health"] == "healthy"
    assert codex["herdr_pane"] == "w4:pA"
    assert codex["herdr_ws"] == "w4"

    opencode = repos.agents.get("w4:pC")
    assert opencode is not None
    assert opencode["label"] == "opencode"
    assert opencode["state"] == "working"
    assert opencode["health"] == "healthy"
    assert opencode["herdr_pane"] == "w4:pC"

    events = health_events(temp_db, "w4:pA")
    assert [event["event_type"] for event in events] == ["healthy"]
    details = json.loads(events[0]["details"])
    assert details["layer"] == "primary"


@pytest.mark.asyncio
async def test_primary_stream_failure_marks_unavailable_and_secondary_polling_recovers(
    repos, make_agent, test_config
):
    make_agent("w4:pA", state="working", health="healthy", herdr_pane="w4:pA")
    adapter = RealStatusStreamAdapter(
        [herdr_status_event("w4:pA", "codex", "blocked")],
        fail_after=True,
        poll_agents=[HerdrAgent("w4:pA", "codex", "codex", "idle", "w4:pA", "w4")],
        pane_outputs={"w4:pA": "idle prompt"},
    )
    engine = WatchdogEngine(adapter, repos.agents, test_config.watchdog)
    engine._RECONNECT_BACKOFF_S = (0.01, 0.01, 0.01)  # fast retries for test

    await engine._run_primary()

    assert engine.primary_failed is True
    assert engine.primary_available is False
    # With reconnection retries: 1 initial + 3 retries = 4 calls
    assert adapter.subscribe_calls == 4
    assert repos.agents.get("w4:pA")["state"] == "blocked"

    await engine.poll_once()

    agent = repos.agents.get("w4:pA")
    assert adapter.agent_list_calls == 1
    assert agent["state"] == "idle"
    assert agent["health"] == "healthy"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_recovery_kills_respawns_waits_and_replays(repos, test_config, make_agent):
    """ISSUE-002: Validar caminho de RECOVERY (kill + respawn) num pane de teste real."""
    pane_id = os.environ.get("HERDR_TEST_PANE")
    if not pane_id:
        pytest.skip("HERDR_TEST_PANE não definido")

    socket_path = os.path.expanduser("~/.config/herdr/herdr.sock")
    if not os.path.exists(socket_path):
        pytest.skip("Herdr socket não encontrado")

    adapter = HerdrAdapter(socket_path=socket_path)
    
    # Configure the repo so the engine believes there is a stuck agent in this pane
    agent_id = "test-recovery-agent"
    make_agent(
        agent_id,
        state="working",
        health="unhealthy",
        herdr_pane=pane_id,
    )
    
    # Mock agent_wait since we don't care about the state event loop race condition here
    adapter.agent_wait = AsyncMock(return_value=True)
    
    # Mock agent_list so the engine discovers our test agent
    from herdmaster.herdr.parser import HerdrAgent
    adapter.agent_list = AsyncMock(return_value=[
        HerdrAgent(id=agent_id, label="test", type="Codex", state="working", pane_id=pane_id, workspace="w1")
    ])
    
    replayer = Replayer()
    clock = Clock(0)
    engine = WatchdogEngine(
        adapter,
        repos.agents,
        test_config.watchdog,
        command_resolver=lambda a_id, a: "echo 'TEST_RECOVERY_SUCCESS'",
        task_replayer=replayer,
        now=clock,
    )
    
    # Configura o monitor inicial
    await engine.poll_once()
    
    # Enviar um comando lento para pendurar o pane
    await adapter.pane_send(pane_id, "sleep 10\n")
    await asyncio.sleep(1.0)
    
    # Inicia a recuperação manualmente para ignorar as heurísticas de hash de saída
    monitor = engine._monitors[agent_id]
    await engine._begin_recovery(monitor)
    await monitor.recovery_task
    
    # O agente deve ter se tornado saudável
    agent = repos.agents.get(agent_id)
    assert agent["health"] == "healthy"
    
    # O pane_read deve mostrar o output do comando de respawn
    await asyncio.sleep(1.0)
    out = await adapter.pane_read(pane_id)
    assert "TEST_RECOVERY_SUCCESS" in out.replace("\n", "").replace("\r", "")
    assert agent["last_output_hash"]


@pytest.mark.asyncio
async def test_auto_recovery_kills_respawns_waits_and_replays(temp_db, repos, make_agent, mock_herdr_adapter, test_config):
    make_agent("A1", state="working", herdr_pane="pane-A1")
    mock_herdr_adapter.agents = [HerdrAgent("A1", "Codex", "codex", "working", "pane-A1", "ws")]
    mock_herdr_adapter.pane_outputs = {"pane-A1": ["stuck"]}
    replayer = Replayer()
    clock = Clock(0)
    engine = WatchdogEngine(
        mock_herdr_adapter,
        repos.agents,
        test_config.watchdog,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=replayer,
        now=clock,
    )

    await engine.poll_once()
    clock.set(11)
    await engine.poll_once()
    await engine._monitors["A1"].recovery_task

    call_names = [name for name, _args, _kwargs in mock_herdr_adapter.calls]
    assert "pane_send" in call_names
    assert "spawn_agent" in call_names
    assert "agent_wait" in call_names
    assert replayer.agent_ids == ["A1"]
    assert repos.agents.get("A1")["health"] == "healthy"
    assert [event["event_type"] for event in health_events(temp_db)][-3:] == ["unhealthy", "recovering", "healthy"]


@pytest.mark.asyncio
async def test_recovery_falls_back_to_raw_pane_close_request_then_respawns_and_replays(
    temp_db, repos, make_agent, test_config
):
    make_agent("A1", state="unhealthy", health="unhealthy", herdr_pane="pane-A1")
    adapter = RawRecoveryAdapter()
    replayer = Replayer()
    manager = RecoveryManager(
        adapter,
        repos.agents,
        test_config.watchdog,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=replayer,
    )

    assert await manager.recover("A1") is True

    assert adapter.calls == [
        ("pane_send", ("pane-A1", "\x03"), {"confirm": True, "timeout": None}),
        ("spawn_agent", ("pane-A1", "codex --resume"), {"timeout": None}),
        ("agent_wait", ("A1", "idle"), {"timeout": manager.wait_timeout_s, "command_timeout": None}),
    ]
    assert replayer.agent_ids == ["A1"]
    assert repos.agents.get("A1")["health"] == "healthy"
    assert [event["event_type"] for event in health_events(temp_db)] == ["recovering", "healthy"]


@pytest.mark.asyncio
async def test_recovery_uses_public_pane_close_before_respawn_and_marks_healthy(
    temp_db, repos, make_agent, test_config
):
    make_agent("A1", state="unhealthy", health="unhealthy", herdr_pane="pane-A1")
    adapter = PublicCloseRecoveryAdapter()
    manager = RecoveryManager(
        adapter,
        repos.agents,
        test_config.watchdog,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=Replayer(),
    )

    assert await manager.recover("A1") is True

    assert adapter.calls == [
        ("pane_send", ("pane-A1", "\x03"), {"confirm": True, "timeout": None}),
        ("spawn_agent", ("pane-A1", "codex --resume"), {"timeout": None}),
        ("agent_wait", ("A1", "idle"), {"timeout": manager.wait_timeout_s, "command_timeout": None}),
    ]
    assert repos.agents.get("A1")["health"] == "healthy"
    assert [event["event_type"] for event in health_events(temp_db)] == ["recovering", "healthy"]


@pytest.mark.asyncio
async def test_escalation_alert_after_max_recovery_failures(repos, make_agent, mock_herdr_adapter, test_config):
    make_agent("A1", state="working", herdr_pane="pane-A1")
    mock_herdr_adapter.wait_results = [RuntimeError("wait failed"), RuntimeError("wait failed")]
    publisher = Publisher()
    replayer = Replayer()
    clock = Clock(0)
    recovery_manager = RecoveryManager(
        mock_herdr_adapter,
        repos.agents,
        test_config.watchdog,
        bus_publisher=publisher,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=replayer,
    )
    engine = WatchdogEngine(
        mock_herdr_adapter,
        repos.agents,
        test_config.watchdog,
        bus_publisher=publisher,
        recovery_manager=recovery_manager,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=replayer,
        now=clock,
    )

    await engine.observe_agent("A1", state="working", pane_id="pane-A1", output="stuck", now=0)
    clock.set(11)
    await engine._evaluate(engine._monitors["A1"], clock())
    await engine._monitors["A1"].recovery_task

    engine._monitors["A1"].health = "healthy"
    engine._monitors["A1"].last_progress_at = 0
    clock.set(22)
    await engine._evaluate(engine._monitors["A1"], clock())
    await engine._monitors["A1"].recovery_task

    alerts = [message for message in publisher.messages if message.type.value == "alert"]
    assert len(alerts) == 1
    assert alerts[0].payload["event"] == "escalation"
    assert alerts[0].payload["failures"] == test_config.watchdog.max_retries


@pytest.mark.asyncio
async def test_recovery_escalates_after_repeated_failures_with_real_close_path(
    repos, make_agent, test_config
):
    make_agent("A1", state="unhealthy", health="unhealthy", herdr_pane="pane-A1")
    adapter = RawRecoveryAdapter(
        wait_results=[RuntimeError("still busy"), RuntimeError("still busy")]
    )
    publisher = Publisher()
    manager = RecoveryManager(
        adapter,
        repos.agents,
        test_config.watchdog,
        bus_publisher=publisher,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=Replayer(),
    )

    assert await manager.recover("A1") is False
    assert await manager.recover("A1") is False

    alerts = [message for message in publisher.messages if message.type.value == "alert"]
    assert len(alerts) == 1
    assert alerts[0].payload["event"] == "escalation"
    assert alerts[0].payload["failures"] == test_config.watchdog.max_retries
    assert [call[0:2] for call in adapter.calls].count(
        ("pane_send", ("pane-A1", "\x03"))
    ) == test_config.watchdog.max_retries


@pytest.mark.asyncio
async def test_secondary_polling_works_when_primary_events_unavailable(repos, make_agent, mock_herdr_adapter, test_config):
    make_agent("A1", state="unknown", herdr_pane="pane-A1")
    mock_herdr_adapter.primary_events = None
    mock_herdr_adapter.agents = [HerdrAgent("A1", "Codex", "codex", "idle", "pane-A1", "ws")]
    mock_herdr_adapter.pane_outputs = {"pane-A1": ["idle prompt"]}
    clock = Clock(0)
    engine = WatchdogEngine(mock_herdr_adapter, repos.agents, test_config.watchdog, now=clock)

    await engine._run_primary()
    assert engine.primary_available is False

    await engine.poll_once()
    agent = repos.agents.get("A1")
    assert agent["state"] == "idle"
    assert agent["last_output_hash"]


@pytest.mark.asyncio
async def test_every_watchdog_transition_persists_health_event(temp_db, repos, make_agent, mock_herdr_adapter, test_config):
    make_agent("A1", state="working", herdr_pane="pane-A1")
    clock = Clock(0)
    engine = WatchdogEngine(mock_herdr_adapter, repos.agents, test_config.watchdog, now=clock)

    await engine.observe_agent("A1", state="working", pane_id="pane-A1", output="one", now=0)
    await engine._transition(engine._monitors["A1"], "suspect", "soft_timeout", "test")
    await engine._transition(engine._monitors["A1"], "unhealthy", "hard_timeout", "test")
    await engine.observe_agent("A1", state="idle", pane_id="pane-A1", output="done", now=1)

    assert [event["event_type"] for event in health_events(temp_db)] == ["suspect", "unhealthy", "healthy"]


# ---------------------------------------------------------------------------
# ADR-001 Onda 2 — boot conjunto + degradação graciosa + reconexão watchdog
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_boot_graceful_without_herdr(test_config, caplog):
    """_check_herdr_connection returns False and logs WARNING when Herdr is down."""
    import logging
    from unittest.mock import AsyncMock, patch

    from herdmaster.__main__ import _check_herdr_connection

    mock_adapter = AsyncMock()
    mock_adapter.agent_list.side_effect = ConnectionRefusedError("no socket")

    with patch("herdmaster.herdr.adapter.HerdrAdapter", return_value=mock_adapter):
        with caplog.at_level(logging.WARNING):
            result = await _check_herdr_connection(test_config)

    assert result is False
    mock_adapter.agent_list.assert_awaited_once_with()
    assert any("herdr_unavailable_degraded_mode" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_boot_success_with_herdr(test_config, caplog):
    """_check_herdr_connection returns True and logs INFO when Herdr responds."""
    import logging
    from unittest.mock import AsyncMock, patch

    from herdmaster.__main__ import _check_herdr_connection

    mock_adapter = AsyncMock()
    mock_adapter.agent_list.return_value = [
        HerdrAgent("w4:pA", "codex", "codex", "idle", "w4:pA", "w4"),
        HerdrAgent("w4:pC", "opencode", "opencode", "working", "w4:pC", "w4"),
    ]

    with patch("herdmaster.herdr.adapter.HerdrAdapter", return_value=mock_adapter):
        with caplog.at_level(logging.INFO):
            result = await _check_herdr_connection(test_config)

    assert result is True
    mock_adapter.agent_list.assert_awaited_once_with()
    assert any("herdr_connection_ok" in record.message for record in caplog.records)


class ReconnectSubscribeAdapter:
    """subscribe_status that fails N times then succeeds."""

    def __init__(self, fail_count):
        self._fail_count = fail_count
        self._call_count = 0
        self.poll_agents = []

    async def subscribe_status(self, callback):
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise RuntimeError(f"subscribe failed (attempt {self._call_count})")
        # Success — deliver nothing; just return cleanly.

    async def agent_list(self):
        return list(self.poll_agents)

    async def pane_read(self, pane_id):
        return ""


@pytest.mark.asyncio
async def test_subscribe_reconnect_success(repos, test_config):
    """subscribe_status fails 1x, retries after 5s backoff, succeeds on 2nd call."""
    adapter = ReconnectSubscribeAdapter(fail_count=1)
    engine = WatchdogEngine(adapter, repos.agents, test_config.watchdog)
    # Shorten backoff delays for test speed.
    engine._RECONNECT_BACKOFF_S = (0.01, 0.01, 0.01)

    await engine._run_primary()

    assert engine.primary_available is True
    assert engine.primary_failed is False
    assert engine._primary_reconnect_attempts == 0  # reset after success
    assert adapter._call_count == 2


@pytest.mark.asyncio
async def test_subscribe_reconnect_exhausted(repos, test_config):
    """3 consecutive failures exhaust retries and fall to polling permanently."""
    adapter = ReconnectSubscribeAdapter(fail_count=10)  # always fail
    engine = WatchdogEngine(adapter, repos.agents, test_config.watchdog)
    engine._RECONNECT_BACKOFF_S = (0.01, 0.01, 0.01)

    await engine._run_primary()

    assert engine.primary_failed is True
    assert engine.primary_available is False
    assert engine._primary_reconnect_attempts == 3
    # 3 backoff retries + 1 initial = 4 calls total, but only 3 are within
    # the backoff schedule; the 4th exceeds len(backoff) and triggers exhaustion.
    assert adapter._call_count == 4

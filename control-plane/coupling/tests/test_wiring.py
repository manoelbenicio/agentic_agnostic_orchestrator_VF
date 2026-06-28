"""Tests for real adapter wiring and graceful fallback."""

from __future__ import annotations

from coupling import CouplingPhase, build_coupled_executors
from coupling import wiring


class FallbackTerminalAdapter:
    pass


class FallbackQueueClient:
    pass


def test_build_coupled_executors_uses_real_adapters_when_available(monkeypatch) -> None:
    monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: True)
    monkeypatch.setattr(wiring, "herdmaster_http_probe", lambda base_url, timeout_s=1.0: True)

    coupled = build_coupled_executors(
        fallback_terminal_adapter=FallbackTerminalAdapter(),
        fallback_queue_client=FallbackQueueClient(),
        herdmaster_url="http://127.0.0.1:8080",
        herdr_socket_path="/tmp/herdr.sock",
    )

    assert coupled.status.phase == CouplingPhase.CONNECTED
    assert type(coupled.terminal.adapter).__name__ == "HerdrRuntimeAdapter"
    assert type(coupled.socket.queue_client).__name__ == "HerdMasterHttpQueueClient"


def test_build_coupled_executors_falls_back_when_unavailable(monkeypatch) -> None:
    terminal_adapter = FallbackTerminalAdapter()
    queue_client = FallbackQueueClient()
    monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)
    monkeypatch.setattr(wiring, "herdmaster_http_probe", lambda base_url, timeout_s=1.0: False)

    coupled = build_coupled_executors(
        fallback_terminal_adapter=terminal_adapter,
        fallback_queue_client=queue_client,
        herdmaster_url="http://127.0.0.1:8080",
    )

    assert coupled.status.phase == CouplingPhase.DEGRADED
    assert "terminal degraded" in str(coupled.status.last_error)
    assert "socket degraded" in str(coupled.status.last_error)
    assert coupled.terminal.adapter is terminal_adapter
    assert coupled.socket.queue_client is queue_client


def test_build_coupled_executors_keeps_real_terminal_when_socket_degraded(monkeypatch) -> None:
    queue_client = FallbackQueueClient()
    monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: True)
    monkeypatch.setattr(wiring, "herdmaster_http_probe", lambda base_url, timeout_s=1.0: False)

    coupled = build_coupled_executors(
        fallback_terminal_adapter=FallbackTerminalAdapter(),
        fallback_queue_client=queue_client,
        herdmaster_url="http://127.0.0.1:8080",
        herdr_socket_path="/tmp/herdr.sock",
    )

    assert coupled.status.phase == CouplingPhase.DEGRADED
    assert "socket degraded" in str(coupled.status.last_error)
    assert "terminal degraded" not in str(coupled.status.last_error)
    assert type(coupled.terminal.adapter).__name__ == "HerdrRuntimeAdapter"
    assert coupled.socket.queue_client is queue_client


def test_build_coupled_executors_keeps_real_socket_when_terminal_degraded(monkeypatch) -> None:
    terminal_adapter = FallbackTerminalAdapter()
    monkeypatch.setattr(wiring, "herdr_socket_probe", lambda socket_path=None: False)
    monkeypatch.setattr(wiring, "herdmaster_http_probe", lambda base_url, timeout_s=1.0: True)

    coupled = build_coupled_executors(
        fallback_terminal_adapter=terminal_adapter,
        fallback_queue_client=FallbackQueueClient(),
        herdmaster_url="http://127.0.0.1:8080",
    )

    assert coupled.status.phase == CouplingPhase.DEGRADED
    assert "terminal degraded" in str(coupled.status.last_error)
    assert "socket degraded" not in str(coupled.status.last_error)
    assert coupled.terminal.adapter is terminal_adapter
    assert type(coupled.socket.queue_client).__name__ == "HerdMasterHttpQueueClient"


def test_herdr_socket_probe_rejects_stale_socket_path(tmp_path) -> None:
    stale_socket = tmp_path / "herdr.sock"
    stale_socket.write_text("", encoding="utf-8")

    assert wiring.herdr_socket_probe(stale_socket, timeout_s=0.01) is False

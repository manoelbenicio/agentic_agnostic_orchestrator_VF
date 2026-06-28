"""Tests for ADR-001 coupling lifecycle behavior."""

from __future__ import annotations

import asyncio

from coupling import CouplingManager, CouplingPhase


async def _no_sleep(_: float) -> None:
    return None


def test_connect_sets_connected_and_is_idempotent() -> None:
    calls = {"herdr": 0, "herdmaster": 0}

    def herdr_probe() -> bool:
        calls["herdr"] += 1
        return True

    def herdmaster_probe() -> bool:
        calls["herdmaster"] += 1
        return True

    manager = CouplingManager(
        herdr_probe=herdr_probe,
        herdmaster_probe=herdmaster_probe,
        backoff_delays=(0.01,),
        sleep=_no_sleep,
    )

    first = asyncio.run(manager.connect())
    second = asyncio.run(manager.connect())

    assert first.phase == CouplingPhase.CONNECTED
    assert second.phase == CouplingPhase.CONNECTED
    assert calls == {"herdr": 1, "herdmaster": 1}


def test_connect_degrades_after_retry_failures() -> None:
    manager = CouplingManager(
        herdr_probe=lambda: True,
        herdmaster_probe=lambda: False,
        backoff_delays=(0.01, 0.02),
        sleep=_no_sleep,
    )

    status = asyncio.run(manager.connect())

    assert status.phase == CouplingPhase.DEGRADED
    assert status.attempts == 3
    assert "HerdMaster probe returned false" in str(status.last_error)


def test_reconnect_recovers_from_degraded_state() -> None:
    attempts = {"count": 0}

    def herdmaster_probe() -> bool:
        attempts["count"] += 1
        return attempts["count"] >= 2

    manager = CouplingManager(
        herdr_probe=lambda: True,
        herdmaster_probe=herdmaster_probe,
        backoff_delays=(),
        sleep=_no_sleep,
    )

    degraded = asyncio.run(manager.connect())
    connected = asyncio.run(manager.reconnect())

    assert degraded.phase == CouplingPhase.DEGRADED
    assert connected.phase == CouplingPhase.CONNECTED


def test_runtime_drop_moves_connected_to_disconnected() -> None:
    healthy = {"value": True}
    manager = CouplingManager(
        herdr_probe=lambda: healthy["value"],
        herdmaster_probe=lambda: True,
        backoff_delays=(),
        sleep=_no_sleep,
    )

    connected = asyncio.run(manager.connect())
    healthy["value"] = False
    dropped = asyncio.run(manager.check_runtime())

    assert connected.phase == CouplingPhase.CONNECTED
    assert dropped.phase == CouplingPhase.DISCONNECTED
    assert "Herdr probe returned false" in str(dropped.last_error)

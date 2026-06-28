from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest

from herdmaster.herdr.adapter import HerdrAdapter
from herdmaster.herdr.parser import HerdrAgent


def _socket_path() -> Path:
    return Path(os.environ.get("HERDR_SOCKET_PATH", "~/.config/herdr/herdr.sock")).expanduser()


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _socket_path().exists(),
        reason="Herdr socket not found; set HERDR_SOCKET_PATH or start Herdr 0.7.0",
    ),
]


@pytest.fixture
def live_adapter() -> HerdrAdapter:
    return HerdrAdapter(socket_path=_socket_path(), timeout=5.0)


async def _first_live_agent(live_adapter: HerdrAdapter) -> HerdrAgent:
    agents = await asyncio.wait_for(live_adapter.agent_list(), timeout=5)
    if not agents:
        pytest.skip("Herdr agent.list returned no live agents")

    requested_pane_id = os.environ.get("HERDR_LIVE_PANE_ID")
    if requested_pane_id:
        for agent in agents:
            if agent.pane_id == requested_pane_id:
                return agent
        pytest.skip(f"HERDR_LIVE_PANE_ID={requested_pane_id!r} was not found in agent.list")

    for agent in agents:
        if agent.pane_id:
            return agent
    pytest.skip("Herdr agent.list returned agents without pane_id values")


@pytest.mark.asyncio
async def test_live_adapter_agent_list(live_adapter: HerdrAdapter) -> None:
    agents = await asyncio.wait_for(live_adapter.agent_list(), timeout=5)
    assert isinstance(agents, list)
    for agent in agents:
        assert isinstance(agent, HerdrAgent)
        assert agent.pane_id
        assert agent.type
        assert agent.state in {"idle", "working", "blocked", "done", "unknown"}


@pytest.mark.asyncio
async def test_live_adapter_subscribe_status(live_adapter: HerdrAdapter) -> None:
    target = await _first_live_agent(live_adapter)
    event_seen = asyncio.Event()
    events: list[dict] = []
    trigger_state = "idle" if target.state == "working" else "working"
    restore_state = target.state if target.state in {"idle", "working", "blocked", "unknown"} else "idle"

    async def callback(event: dict) -> None:
        events.append(event)
        payload = event.get("result") if isinstance(event.get("result"), dict) else event
        if isinstance(payload.get("data"), dict):
            payload = {**payload["data"], "type": payload.get("event") or payload["data"].get("type")}
        if (
            payload.get("type") == "pane.agent_status_changed"
            and payload.get("pane_id") == target.pane_id
        ):
            event_seen.set()

    task = asyncio.create_task(live_adapter.subscribe_status(callback))
    try:
        await asyncio.sleep(0.25)
        await live_adapter._request(
            "pane.report_agent",
            {
                "pane_id": target.pane_id,
                "source": "herdmaster-live-test",
                "agent": target.type or "herdmaster-live-test",
                "state": trigger_state,
                "custom_status": "HerdMaster live integration test",
            },
            timeout=5,
        )
        await asyncio.wait_for(event_seen.wait(), timeout=10)
    finally:
        await live_adapter._request(
            "pane.report_agent",
            {
                "pane_id": target.pane_id,
                "source": "herdmaster-live-test",
                "agent": target.type or "herdmaster-live-test",
                "state": restore_state,
                "custom_status": "",
            },
            timeout=5,
        )
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert events


@pytest.mark.asyncio
async def test_live_adapter_pane_send_and_read(live_adapter: HerdrAdapter) -> None:
    target = await _first_live_agent(live_adapter)
    marker = f"HM_LIVE_{uuid4().hex}"

    await live_adapter.pane_send(target.pane_id, f"printf '{marker}\\n'\n", timeout=5)

    output = ""
    for _ in range(20):
        await asyncio.sleep(0.25)
        output = await live_adapter.pane_read(target.pane_id, timeout=5)
        if marker in output:
            break

    assert marker in output

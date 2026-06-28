from __future__ import annotations

import pytest

from herdmaster.config import AclConfig, AclRole
from herdmaster.herdr.parser import HerdrAgent
from herdmaster.watchdog.engine import WatchdogEngine


@pytest.mark.asyncio
async def test_watchdog_poll_syncs_herdr_agents_into_agent_table(
    repos,
    mock_herdr_adapter,
    test_config,
):
    mock_herdr_adapter.agents = [
        HerdrAgent("A1", "Codex 1", "codex", "idle", "pane-A1", "HerdMaster"),
        HerdrAgent("A2", "Claude 2", "claude", "working", "pane-A2", "HerdMaster"),
    ]

    engine = WatchdogEngine(mock_herdr_adapter, repos.agents, test_config.watchdog)

    assert repos.agents.list() == []

    await engine.poll_once()

    agents = {agent["id"]: agent for agent in repos.agents.list()}
    assert set(agents) == {"A1", "A2"}
    assert agents["A1"]["label"] == "Codex 1"
    assert agents["A1"]["type"] == "codex"
    assert agents["A1"]["state"] == "idle"
    assert agents["A1"]["herdr_pane"] == "pane-A1"
    assert agents["A1"]["herdr_ws"] == "HerdMaster"
    assert agents["A2"]["label"] == "Claude 2"
    assert agents["A2"]["type"] == "claude"
    assert agents["A2"]["state"] == "working"
    assert agents["A2"]["herdr_pane"] == "pane-A2"
    assert agents["A2"]["herdr_ws"] == "HerdMaster"


@pytest.mark.asyncio
async def test_watchdog_sync_applies_acl_role_for_tech_lead(
    repos,
    mock_herdr_adapter,
    test_config,
):
    mock_herdr_adapter.agents = [
        HerdrAgent("w8:pJ", "Kiro TL", "kiro", "idle", "w8:pJ", "w8"),
    ]
    acl = AclConfig(
        default_policy="deny",
        roles=(
            AclRole(
                name="orchestrator",
                agents=["w8:pJ"],
                can_send_to=["*"],
                can_receive_from=["*"],
                can_dispatch_tasks=True,
                can_reassign_tasks=True,
            ),
        ),
    )

    engine = WatchdogEngine(mock_herdr_adapter, repos.agents, test_config.watchdog, acl_config=acl)

    await engine.poll_once()

    assert repos.agents.get("w8:pJ")["role"] == "orchestrator"

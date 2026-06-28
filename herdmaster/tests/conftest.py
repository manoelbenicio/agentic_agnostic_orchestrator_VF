"""Shared pytest fixtures for HerdMaster stable subsystem tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from herdmaster.config import (
    AclConfig,
    ApiConfig,
    BusConfig,
    HerdMasterConfig,
    LoggingConfig,
    PathsConfig,
    WatchdogConfig,
)
from herdmaster.db import schema
from herdmaster.db.repositories import AgentRepo, MessageRepo, ProjectRepo, TaskRepo
from herdmaster.herdr.parser import HerdrAgent


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: live Herdr tests (skip in CI)")


def pytest_collection_modifyitems(config, items):
    if "integration" in (config.option.markexpr or ""):
        return
    skip_integration = pytest.mark.skip(reason="integration test skipped by default; run with -m integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def temp_db(tmp_path):
    """Return an initialized temporary Postgres connection using schema.connect/init_db."""
    schema_name = "hm_test_" + hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:16]
    conn = schema.connect(tmp_path / "herdmaster-test.db", schema_name=schema_name)
    schema.init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def repos(temp_db):
    """Return repository instances bound to the temporary database connection."""
    return SimpleNamespace(
        agents=AgentRepo(temp_db),
        tasks=TaskRepo(temp_db),
        messages=MessageRepo(temp_db),
        projects=ProjectRepo(temp_db),
    )


@dataclass
class MockHerdrAdapter:
    """Scriptable in-memory HerdrAdapter test double with no subprocess usage."""

    agents: list[HerdrAgent] = field(default_factory=list)
    pane_outputs: dict[str, list[str]] = field(default_factory=dict)
    wait_results: list[bool | BaseException] = field(default_factory=list)
    primary_events: list[dict[str, Any]] | None = None
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def agent_list(self):
        self.calls.append(("agent_list", (), {}))
        return list(self.agents)

    async def pane_read(self, pane_id: str):
        self.calls.append(("pane_read", (pane_id,), {}))
        values = self.pane_outputs.get(pane_id, [""])
        if len(values) > 1:
            return values.pop(0)
        return values[0] if values else ""

    async def pane_send(self, pane_id: str, text: str, *, confirm: bool = True, timeout=None):
        self.calls.append(("pane_send", (pane_id, text), {"confirm": confirm, "timeout": timeout}))

    async def spawn_agent(self, pane_id: str, command: str, *, timeout=None):
        self.calls.append(("spawn_agent", (pane_id, command), {"timeout": timeout}))

    async def agent_wait(self, agent_id: str, state: str = "idle", timeout: int = 60, *, command_timeout=None):
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

    async def subscribe_state_changes(self):
        if self.primary_events is None:
            raise RuntimeError("primary unavailable")
        for event in self.primary_events:
            yield event


@pytest.fixture
def mock_herdr_adapter():
    """Return a fake Herdr adapter with scriptable agents, pane output, and wait results."""
    return MockHerdrAdapter()


@pytest.fixture
def test_config(tmp_path):
    """Return a HerdMasterConfig rooted in pytest tmp_path with short watchdog timeouts."""
    config_dir = tmp_path / "config"
    return HerdMasterConfig(
        paths=PathsConfig(
            config_dir=config_dir,
            db=config_dir / "herdmaster.db",
            socket=config_dir / "herdmaster.sock",
            log=config_dir / "herdmaster.log",
        ),
        watchdog=WatchdogConfig(
            soft_timeout_s=5.0,
            hard_timeout_s=10.0,
            poll_interval_s=1,
            max_retries=2,
            tertiary_hash_interval_s=2,
        ),
        bus=BusConfig(socket_path=config_dir / "herdmaster.sock", message_ttl_s=2),
        acl=AclConfig.defaults(),
        api=ApiConfig.defaults(),
        logging=LoggingConfig.defaults(),
    )


@pytest.fixture
def make_agent(repos):
    """Factory that inserts an agent row and returns the stored dict."""

    def _make_agent(agent_id="A1", **overrides):
        values = {
            "label": f"Agent {agent_id}",
            "agent_type": "codex",
            "role": "worker",
            "herdr_pane": f"pane-{agent_id}",
            "herdr_ws": "HerdMaster",
            "state": "unknown",
            "health": "healthy",
            "strengths": ["testing"],
        }
        values.update(overrides)
        return repos.agents.upsert(agent_id, **values)

    return _make_agent


@pytest.fixture
def make_task(repos):
    """Factory that creates a task row and returns its task id."""

    def _make_task(title="Task", prompt="Do the task", **overrides):
        return repos.tasks.create(title=title, prompt=prompt, **overrides)

    return _make_task


@pytest.fixture
def make_message(repos):
    """Factory that inserts a message row and returns its message id."""

    def _make_message(message_type="chat", payload=None, **overrides):
        return repos.messages.insert(message_type, {} if payload is None else payload, **overrides)

    return _make_message

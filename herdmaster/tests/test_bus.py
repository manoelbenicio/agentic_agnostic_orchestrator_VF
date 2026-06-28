from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from herdmaster.bus.messages import MessageType, group_name, is_broadcast, is_group, new_message
from herdmaster.bus.server import MessageBusServer
from herdmaster.config import BusConfig


def test_message_round_trips_all_six_types():
    for message_type in MessageType:
        msg = new_message(message_type, "A1", "A2", {"type": message_type.value}, correlation_id="corr")
        parsed = msg.from_json(msg.to_json())
        assert parsed.type is message_type
        assert parsed.from_agent == "A1"
        assert parsed.to == "A2"
        assert parsed.payload == {"type": message_type.value}
        assert parsed.correlation_id == "corr"


def test_message_ttl_expiry():
    msg = new_message("heartbeat", "A1", "A2", ttl_seconds=5)
    created = datetime.fromisoformat(msg.timestamp.replace("Z", "+00:00"))
    assert msg.is_expired(created + timedelta(seconds=4)) is False
    assert msg.is_expired(created + timedelta(seconds=5)) is True


def test_address_helpers_identify_unicast_broadcast_and_groups():
    assert is_broadcast("broadcast") is True
    assert is_broadcast("A2") is False
    assert is_group("group:reviewers") is True
    assert group_name("group:reviewers") == "reviewers"
    assert is_group("group:") is False


@pytest.mark.asyncio
async def test_bus_routes_unicast_broadcast_and_group(repos, test_config):
    server = MessageBusServer(test_config.bus, repo=repos.messages, max_queue_size=10)
    server.register("A1")
    server.register("A2")
    server.register("A3")
    server.subscribe_to_group("A2", "reviewers")
    server.subscribe_to_group("A3", "reviewers")

    await server.send(new_message("chat", "A1", "A2", {"kind": "unicast"}))
    assert (await server._queues["A2"].get()).payload == {"kind": "unicast"}
    assert server._queues["A1"].empty()
    assert server._queues["A3"].empty()

    await server.send(new_message("alert", "A1", "broadcast", {"kind": "broadcast"}))
    assert (await server._queues["A1"].get()).payload == {"kind": "broadcast"}
    assert (await server._queues["A2"].get()).payload == {"kind": "broadcast"}
    assert (await server._queues["A3"].get()).payload == {"kind": "broadcast"}

    await server.send(new_message("task_update", "A1", "group:reviewers", {"kind": "group"}))
    assert server._queues["A1"].empty()
    assert (await server._queues["A2"].get()).payload == {"kind": "group"}
    assert (await server._queues["A3"].get()).payload == {"kind": "group"}


def test_message_repo_persistence_and_expiry(repos):
    repos.agents.upsert("A1", "Agent 1", "codex", "worker")
    repos.agents.upsert("A2", "Agent 2", "codex", "worker")
    old = (datetime.now(UTC) - timedelta(seconds=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    keep = repos.messages.insert("chat", {"keep": True}, from_agent="A1", to_agent="A2")
    expired = repos.messages.insert("chat", {"drop": True}, from_agent="A1", to_agent="A2", expires_at=old)

    assert {m["id"] for m in repos.messages.list(to_agent="A2", delivered=False)} == {keep, expired}
    assert repos.messages.expire() == 1
    assert [m["id"] for m in repos.messages.list(to_agent="A2", delivered=False)] == [keep]


@pytest.mark.asyncio
async def test_socket_bind_failure_activates_file_fallback_without_raising(monkeypatch, repos, tmp_path):
    async def fail_bind(*args, **kwargs):
        raise OSError("cannot bind")

    monkeypatch.setattr("asyncio.start_unix_server", fail_bind)
    bus_config = BusConfig(socket_path=tmp_path / "bus" / "herdmaster.sock", message_ttl_s=30)
    server = MessageBusServer(bus_config, repo=repos.messages)

    await server.start()
    try:
        assert server._using_fallback is True
        msg = new_message("chat", "A1", "A2", {"fallback": True})
        await server.send(msg)
        stored = await server._fallback.read_messages()
        assert [m.id for m in stored] == [msg.id]
    finally:
        await server.stop()

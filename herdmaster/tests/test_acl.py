from __future__ import annotations

import pytest

from herdmaster.acl.engine import AclEngine, AclDenied
from herdmaster.config import AclConfig, AclRole
from herdmaster.bus.messages import Message, MessageType


@pytest.fixture
def acl_config() -> AclConfig:
    # Setup roles for the tests:
    # 1. orchestrator: wildcard matches orchestrator-*
    #    can_send_to and can_receive_from is *
    #    can_dispatch_tasks = True
    #    can_reassign_tasks = True
    role_orchestrator = AclRole(
        name="orchestrator",
        agents=["orchestrator-*"],
        can_send_to=["*"],
        can_receive_from=["*"],
        can_dispatch_tasks=True,
        can_reassign_tasks=True,
    )

    # 2. worker: wildcard matches worker-*
    #    can_send_to is ["orchestrator-*"] (can send to orchestrator, not other workers)
    #    can_receive_from is ["orchestrator-*"] (can receive from orchestrator, not other workers)
    #    can_dispatch_tasks = False
    #    can_reassign_tasks = False
    role_worker = AclRole(
        name="worker",
        agents=["worker-*"],
        can_send_to=["orchestrator-*"],
        can_receive_from=["orchestrator-*"],
        can_dispatch_tasks=False,
        can_reassign_tasks=False,
    )

    # 3. group_receiver: matches group:workers
    role_group_receiver = AclRole(
        name="group_receiver",
        agents=["group:workers"],
        can_send_to=[],
        can_receive_from=["orchestrator-*"],
        can_dispatch_tasks=False,
        can_reassign_tasks=False,
    )

    return AclConfig(
        default_policy="deny",
        roles=(role_orchestrator, role_worker, role_group_receiver),
    )


@pytest.fixture
def acl_engine(acl_config) -> AclEngine:
    return AclEngine(acl_config)


def test_acl_default_deny(acl_engine):
    # Agents not matching any configured role should be denied (default-deny policy)
    assert not acl_engine.can_send("stranger-1", "worker-1")
    assert not acl_engine.can_send("worker-1", "stranger-1")
    assert not acl_engine.can_send("stranger-1", "orchestrator-1")
    
    # orchestrator-1 has an explicit * rule in can_send_to, so it is allowed to send to stranger-1
    assert acl_engine.can_send("orchestrator-1", "stranger-1")
    
    # Also verify stranger has no roles
    assert acl_engine.get_roles_for_agent("stranger-1") == set()


def test_acl_orchestrator_allowed(acl_engine):
    # orchestrator-* should be allowed to send to anyone/receive from anyone
    assert acl_engine.can_send("orchestrator-1", "orchestrator-2")
    assert acl_engine.can_send("orchestrator-1", "worker-1")
    assert acl_engine.can_send("worker-1", "orchestrator-1")


def test_acl_worker_to_orchestrator_allowed_worker_to_worker_denied(acl_engine):
    # TC-005: worker -> orchestrator allowed, worker -> worker DENIED
    assert acl_engine.can_send("worker-1", "orchestrator-1")
    assert not acl_engine.can_send("worker-1", "worker-2")


def test_acl_can_dispatch_only_orchestrator(acl_engine):
    assert acl_engine.can_dispatch("orchestrator-1")
    assert not acl_engine.can_dispatch("worker-1")
    assert not acl_engine.can_dispatch("stranger-1")

    assert acl_engine.can_reassign("orchestrator-1")
    assert not acl_engine.can_reassign("worker-1")
    assert not acl_engine.can_reassign("stranger-1")


def test_acl_check_message_raises_denied(acl_engine):
    # Valid message worker -> orchestrator (should not raise)
    msg_ok = Message(
        id="123",
        type=MessageType.CHAT,
        from_agent="worker-1",
        to="orchestrator-1",
        correlation_id=None,
        timestamp="2026-06-21T23:00:00Z",
    )
    acl_engine.check_message(msg_ok)

    # Invalid message worker -> worker (should raise AclDenied)
    msg_denied = Message(
        id="124",
        type=MessageType.CHAT,
        from_agent="worker-1",
        to="worker-2",
        correlation_id=None,
        timestamp="2026-06-21T23:00:00Z",
    )
    with pytest.raises(AclDenied) as exc_info:
        acl_engine.check_message(msg_denied)
    
    assert exc_info.value.from_agent == "worker-1"
    assert exc_info.value.to_agent == "worker-2"
    assert "deny" in exc_info.value.reason.lower() or "explicit" in exc_info.value.reason.lower() or "default" in exc_info.value.reason.lower() or "no roles" in exc_info.value.reason.lower()


def test_acl_wildcard_agents_resolution(acl_engine):
    assert acl_engine.get_roles_for_agent("orchestrator-foo") == {"orchestrator"}
    assert acl_engine.get_roles_for_agent("worker-bar") == {"worker"}


def test_acl_broadcast_gating(acl_engine):
    # Orchestrator should be allowed to broadcast, worker should not
    assert acl_engine.can_send("orchestrator-1", "broadcast")
    assert not acl_engine.can_send("worker-1", "broadcast")


def test_acl_group_routing(acl_engine):
    # Send to group:workers should resolve to group_receiver role
    # orchestrator-* can send to group:workers because orchestrator can send to * (explicitly allowed)
    assert acl_engine.can_send("orchestrator-1", "group:workers")
    
    # worker-* can NOT send to group:workers because they can only send to orchestrator-*,
    # and group_receiver does not receive from worker-*
    assert not acl_engine.can_send("worker-1", "group:workers")


def test_acl_hot_swap_config(acl_engine):
    # Initially worker -> worker is denied
    assert not acl_engine.can_send("worker-1", "worker-2")

    # Swap to new config where default_policy is allow
    # Note: we must keep the role configuration so that the sender is assigned a role
    new_config = AclConfig(
        default_policy="allow",
        roles=(
            AclRole(
                name="worker",
                agents=["worker-*"],
                can_send_to=[],
                can_receive_from=[],
                can_dispatch_tasks=False,
                can_reassign_tasks=False,
            ),
        ),
    )
    acl_engine.swap_config(new_config)

    assert acl_engine.config == new_config
    assert len(acl_engine.roles) == 1
    assert acl_engine.can_send("worker-1", "worker-2")


def test_acl_set_role_runtime_assignment(acl_engine):
    # stranger-1 has no role initially
    assert acl_engine.get_roles_for_agent("stranger-1") == set()
    assert not acl_engine.can_send("stranger-1", "orchestrator-1")

    # Set role to worker
    acl_engine.set_role("stranger-1", "worker")
    assert acl_engine.get_roles_for_agent("stranger-1") == {"worker"}
    assert acl_engine.can_send("stranger-1", "orchestrator-1")

    # Set to admin/orchestrator
    acl_engine.set_role("stranger-1", "orchestrator")
    assert acl_engine.get_roles_for_agent("stranger-1") == {"orchestrator"}
    assert acl_engine.can_send("stranger-1", "worker-1")

    # Setting nonexistent role should raise ValueError
    with pytest.raises(ValueError):
        acl_engine.set_role("stranger-1", "nonexistent")


def test_acl_with_test_config(test_config):
    # test_config.acl is AclConfig.defaults()
    # It has default_policy="deny" and no roles
    engine = AclEngine(test_config.acl)
    assert not engine.can_send("orchestrator-1", "worker-1")

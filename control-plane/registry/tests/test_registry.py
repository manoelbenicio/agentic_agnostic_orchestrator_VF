from __future__ import annotations

import pytest

from registry.models import AgentStatus, EnrollmentDecision, PaneRef
from registry.propagation import AllowlistPropagationHook, PropagationEvent, PropagationUnavailable


def test_phantom_workspace_discovery_is_ignored_without_db_write(service):
    pane = PaneRef(workspace_id="foreign-workspace", pane_id="w9:p1")

    result = service.discover_pane(pane)

    assert result.decision == EnrollmentDecision.IGNORED
    assert result.wrote_to_db is False
    assert service.repository.count_agents() == 0


def test_enroll_pane_registers_once_and_propagates_to_all_hooks(service, hooks):
    pane = PaneRef(workspace_id="workspace-main", pane_id="w1:p1", session_id="session-a")

    result = service.enroll_pane(
        pane,
        tenant_id="tenant-a",
        label="Codex Worker 1",
        vendor="codex",
        role="worker",
        stable_key="tenant-a/codex-worker-1",
        metadata={"strengths": ["tests"]},
    )

    assert result.decision == EnrollmentDecision.ENROLLED
    assert result.wrote_to_db is True
    assert result.agent is not None
    assert result.agent.agent_id.startswith("agent-")
    assert result.agent.workspace_id == "workspace-main"
    assert result.agent.pane_id == "w1:p1"
    assert result.agent.metadata == {"strengths": ["tests"]}
    assert service.repository.count_agents() == 1

    for hook in hooks:
        assert [event.action for event in hook.events] == ["agent.added"]
        assert hook.events[0].agent.agent_id == result.agent.agent_id


def test_remove_agent_is_single_action_and_propagates_cleanup(service, hooks):
    enrolled = service.enroll_pane(
        PaneRef(workspace_id="workspace-main", pane_id="w1:p2"),
        tenant_id="tenant-a",
        label="Kiro Reviewer",
        vendor="kiro",
        role="peer_reviewer",
    )
    agent_id = enrolled.agent.agent_id

    removed = service.remove_agent(agent_id, reason="pane removed")

    assert removed is not None
    assert removed.agent_id == agent_id
    assert removed.status == AgentStatus.REMOVED
    assert removed.workspace_id is None
    assert removed.pane_id is None
    assert service.repository.get(agent_id).status == AgentStatus.REMOVED

    for hook in hooks:
        assert [event.action for event in hook.events] == ["agent.added", "agent.removed"]
        assert hook.events[-1].reason == "pane removed"


def test_stable_identity_survives_pane_churn_and_preserves_history(service, hooks):
    enrolled = service.enroll_pane(
        PaneRef(workspace_id="workspace-main", pane_id="w6:p1", session_id="before"),
        tenant_id="tenant-a",
        label="Antigravity Planner",
        vendor="antigravity",
        role="orchestrator",
        stable_key="tenant-a/ag-planner",
    )
    original = enrolled.agent

    updated = service.update_pane(
        original.agent_id,
        PaneRef(workspace_id="workspace-main", pane_id="w6:p7", session_id="after"),
    )

    assert updated is not None
    assert updated.agent_id == original.agent_id
    assert updated.stable_key == "tenant-a/ag-planner"
    assert updated.pane_id == "w6:p7"

    history = service.repository.mapping_history(original.agent_id)
    assert [(row["pane_id"], row["session_id"]) for row in history] == [
        ("w6:p1", "before"),
        ("w6:p7", "after"),
    ]
    assert history[0]["retired_at"] is not None
    assert history[1]["retired_at"] is None

    for hook in hooks:
        assert [event.action for event in hook.events] == [
            "agent.added",
            "agent.pane_updated",
        ]


def test_discover_existing_pane_returns_stable_identity_without_write(service):
    pane = PaneRef(workspace_id="workspace-main", pane_id="w2:p1")
    enrolled = service.enroll_pane(
        pane,
        tenant_id="tenant-a",
        label="Gemini Worker",
        vendor="gemini",
        role="worker",
    )

    discovered = service.discover_pane(pane)

    assert discovered.decision == EnrollmentDecision.ALREADY_ENROLLED
    assert discovered.wrote_to_db is False
    assert discovered.agent.agent_id == enrolled.agent.agent_id
    assert service.repository.count_agents() == 1


class RealAllowlistTarget:
    def __init__(self) -> None:
        self.allowed: set[str] = set()

    def propagate_agent_added(self, event: PropagationEvent) -> None:
        self.allowed.add(event.agent.agent_id)

    def propagate_agent_removed(self, event: PropagationEvent) -> None:
        self.allowed.discard(event.agent.agent_id)


def test_allowlist_hook_propagates_to_real_target(registry_conn):
    target = RealAllowlistTarget()
    hook = AllowlistPropagationHook(target)
    from registry.repository import AgentRegistryRepository
    from registry.service import AgentRegistryService

    service = AgentRegistryService(
        repository=AgentRegistryRepository(registry_conn),
        propagation=hook,
        enrolled_workspaces={"workspace-main"},
    )

    enrolled = service.enroll_pane(
        PaneRef(workspace_id="workspace-main", pane_id="w-real:p1"),
        tenant_id="tenant-a",
        label="Real Worker",
        vendor="codex",
        role="worker",
    )

    assert enrolled.agent.agent_id in target.allowed

    service.remove_agent(enrolled.agent.agent_id, reason="cleanup")

    assert enrolled.agent.agent_id not in target.allowed


def test_propagation_without_target_fails_explicitly(service):
    agent = service.enroll_pane(
        PaneRef(workspace_id="workspace-main", pane_id="w-fail:p1"),
        tenant_id="tenant-a",
        label="Fail Worker",
        vendor="codex",
        role="worker",
    ).agent
    hook = AllowlistPropagationHook()

    with pytest.raises(PropagationUnavailable, match="allowlist propagation target unavailable"):
        hook.propagate(PropagationEvent(action="agent.added", agent=agent))

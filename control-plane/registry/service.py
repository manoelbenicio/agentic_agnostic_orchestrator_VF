"""Application service for one-action registry enrollment and propagation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import AgentRecord, DiscoveredPane, EnrollmentDecision, PaneRef
from .propagation import CompositePropagationHook, PropagationEvent, PropagationHook
from .repository import AgentRegistryRepository


@dataclass(slots=True)
class AgentRegistryService:
    """High-level registry API enforcing discovery, enrollment, and propagation."""

    repository: AgentRegistryRepository
    propagation: PropagationHook = field(default_factory=CompositePropagationHook.default)
    enrolled_workspaces: set[str] = field(default_factory=set)

    def discover_pane(self, pane: PaneRef) -> DiscoveredPane:
        """Reconcile a pane discovery without writing phantom panes by default."""
        existing = self.repository.find_by_pane(pane)
        if existing is not None:
            return DiscoveredPane(
                pane=pane,
                decision=EnrollmentDecision.ALREADY_ENROLLED,
                agent=existing,
                reason="pane already maps to a stable agent identity",
                wrote_to_db=False,
            )
        if pane.workspace_id not in self.enrolled_workspaces:
            return DiscoveredPane(
                pane=pane,
                decision=EnrollmentDecision.IGNORED,
                reason="workspace is not enrolled",
                wrote_to_db=False,
            )
        return DiscoveredPane(
            pane=pane,
            decision=EnrollmentDecision.CANDIDATE,
            reason="workspace enrolled; pane can be enrolled in one action",
            wrote_to_db=False,
        )

    def add_agent(
        self,
        *,
        tenant_id: str,
        label: str,
        vendor: str,
        role: str,
        pane: PaneRef | None = None,
        stable_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRecord:
        """Register an agent once and propagate derived consumers automatically."""
        agent = self.repository.create_agent(
            tenant_id=tenant_id,
            label=label,
            vendor=vendor,
            role=role,
            pane=pane,
            stable_key=stable_key,
            metadata=metadata,
        )
        self._propagate("agent.added", agent)
        return agent

    def enroll_pane(
        self,
        pane: PaneRef,
        *,
        tenant_id: str,
        label: str,
        vendor: str,
        role: str,
        stable_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DiscoveredPane:
        """Enroll a legitimate discovered pane in one call."""
        discovery = self.discover_pane(pane)
        if discovery.decision == EnrollmentDecision.IGNORED:
            return discovery
        if discovery.decision == EnrollmentDecision.ALREADY_ENROLLED:
            return discovery
        agent = self.add_agent(
            tenant_id=tenant_id,
            label=label,
            vendor=vendor,
            role=role,
            pane=pane,
            stable_key=stable_key,
            metadata=metadata,
        )
        return DiscoveredPane(
            pane=pane,
            decision=EnrollmentDecision.ENROLLED,
            agent=agent,
            reason="pane enrolled as a stable agent identity",
            wrote_to_db=True,
        )

    def remove_agent(self, agent_id: str, *, reason: str = "") -> AgentRecord | None:
        """Remove an agent once and propagate all downstream derivations."""
        agent = self.repository.remove_agent(agent_id)
        if agent is not None:
            self._propagate("agent.removed", agent, reason=reason)
        return agent

    def update_pane(self, agent_id: str, pane: PaneRef) -> AgentRecord | None:
        """Map a stable internal identity to a new pane after Herdr pane churn."""
        agent = self.repository.remap_pane(agent_id, pane)
        if agent is not None:
            self._propagate("agent.pane_updated", agent)
        return agent

    def _propagate(self, action: str, agent: AgentRecord, *, reason: str = "") -> None:
        self.propagation.propagate(PropagationEvent(action=action, agent=agent, reason=reason))

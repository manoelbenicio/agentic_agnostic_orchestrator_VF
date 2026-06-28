"""Policy-based ACL engine for HerdMaster."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import Any

from herdmaster.bus.messages import Message, is_broadcast, is_group
from herdmaster.config import AclConfig, AclRole

log = logging.getLogger(__name__)


class AclDenied(Exception):
    """Raised when an ACL check fails and the operation is denied."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        reason: str,
        roles_checked: list[str] | None = None,
    ) -> None:
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.reason = reason
        self.roles_checked = roles_checked or []
        super().__init__(
            f"ACL denied: {from_agent} -> {to_agent}: {reason}"
        )


@dataclass(slots=True)
class _AgentRoleMap:
    """Internal mapping of agent -> roles."""

    agent_to_roles: dict[str, set[str]] = field(default_factory=dict)
    role_to_agents: dict[str, set[str]] = field(default_factory=dict)

    def add(self, agent: str, role_name: str) -> None:
        self.agent_to_roles.setdefault(agent, set()).add(role_name)
        self.role_to_agents.setdefault(role_name, set()).add(agent)

    def remove_agent(self, agent: str) -> None:
        roles = self.agent_to_roles.pop(agent, set())
        for role in roles:
            self.role_to_agents.get(role, set()).discard(agent)

    def get_roles(self, agent: str) -> set[str]:
        roles = set()
        for pattern, pattern_roles in self.agent_to_roles.items():
            if pattern == "*" or fnmatch.fnmatchcase(agent, pattern):
                roles.update(pattern_roles)
        return roles

    def get_agents_in_role(self, role_name: str) -> set[str]:
        return self.role_to_agents.get(role_name, set())


class AclEngine:
    """
    Policy-based access control engine.

    Constructed from an already-parsed AclConfig (from herdmaster.config).
    Supports role-based permissions with wildcards, groups, broadcast,
    and dynamic role changes.
    """

    def __init__(self, config: AclConfig) -> None:
        self._config = config
        self._roles: dict[str, AclRole] = {r.name: r for r in config.roles}
        self._agent_roles = _AgentRoleMap()
        self._default_policy = config.default_policy.lower()
        self._build_agent_role_map()

    def _build_agent_role_map(self) -> None:
        """Build the agent -> roles mapping from role definitions."""
        self._agent_roles = _AgentRoleMap()
        for role in self._config.roles:
            for agent_pattern in role.agents:
                if agent_pattern == "*":
                    self._agent_roles.add("*", role.name)
                else:
                    self._agent_roles.add(agent_pattern, role.name)

    def _matches_pattern(self, pattern: str, value: str) -> bool:
        """Check if a value matches a pattern (supports * wildcards)."""
        return fnmatch.fnmatchcase(value, pattern)

    def _agent_matches_pattern(self, pattern: str, agent: str) -> bool:
        """Check if an agent matches a pattern, considering wildcards."""
        if pattern == "*":
            return True
        if self._matches_pattern(pattern, agent):
            return True
        return False

    def _resolve_target_roles(self, target: str) -> set[str]:
        """Resolve all roles that a target agent/group/broadcast actually has."""
        roles = set()

        if is_broadcast(target):
            return roles

        if is_group(target):
            group_name = target.split(":", 1)[1]
            for role in self._config.roles:
                for agent_pattern in role.agents:
                    if self._agent_matches_pattern(agent_pattern, f"group:{group_name}"):
                        roles.add(role.name)
            return roles

        return self.get_roles_for_agent(target)

    def _check_send_allowed(
        self, from_agent: str, to_agent: str
    ) -> tuple[bool, str, list[str]]:
        """
        Check if from_agent can send to to_agent.

        Returns (allowed, reason, roles_checked).
        """
        from_roles = self._agent_roles.get_roles(from_agent)

        if not from_roles:
            return False, "no roles assigned to sender", []

        target_roles = self._resolve_target_roles(to_agent)

        roles_checked = []
        for from_role_name in from_roles:
            from_role = self._roles.get(from_role_name)
            if not from_role:
                continue
            roles_checked.append(from_role_name)

            for send_pattern in from_role.can_send_to:
                if self._agent_matches_pattern(send_pattern, to_agent):
                    return True, "explicit allow in can_send_to", roles_checked

        for to_role_name in target_roles:
            to_role = self._roles.get(to_role_name)
            if not to_role:
                continue
            for recv_pattern in to_role.can_receive_from:
                if self._agent_matches_pattern(recv_pattern, from_agent):
                    return True, "explicit allow in can_receive_from", roles_checked

        if self._default_policy == "allow":
            return True, "default policy allow", roles_checked

        # Default-deny is intentional: any sender/recipient pair without an
        # explicit can_send_to or can_receive_from allow is rejected.
        return False, "default policy deny", roles_checked

    def can_send(self, from_agent: str, to_agent: str) -> bool:
        """
        Check if from_agent is allowed to send a message to to_agent.

        Honors role can_send_to/can_receive_from, wildcards (*),
        group:<name>, broadcast, and default_policy (deny unless allowed).
        """
        allowed, reason, roles_checked = self._check_send_allowed(
            from_agent, to_agent
        )
        if not allowed:
            log.warning(
                "ACL deny: %s -> %s (%s), roles_checked=%s",
                from_agent,
                to_agent,
                reason,
                roles_checked,
            )
        return allowed

    def can_dispatch(self, agent: str) -> bool:
        """
        Check if agent has permission to dispatch tasks.

        Only agents with a role that has can_dispatch_tasks=True can dispatch.
        """
        roles = self._agent_roles.get_roles(agent)
        if not roles and "*" in self._agent_roles.get_roles("*"):
            roles = self._agent_roles.get_roles("*")

        for role_name in roles:
            role = self._roles.get(role_name)
            if role and role.can_dispatch_tasks:
                return True
        return False

    def can_reassign(self, agent: str) -> bool:
        """
        Check if agent has permission to reassign tasks.

        Only agents with a role that has can_reassign_tasks=True can reassign.
        """
        roles = self._agent_roles.get_roles(agent)
        if not roles and "*" in self._agent_roles.get_roles("*"):
            roles = self._agent_roles.get_roles("*")

        for role_name in roles:
            role = self._roles.get(role_name)
            if role and role.can_reassign_tasks:
                return True
        return False

    def check_message(self, msg: Message) -> None:
        """
        Validate a message against ACL rules.

        Raises AclDenied if the send is not permitted.
        """
        allowed, reason, roles_checked = self._check_send_allowed(
            msg.from_agent, msg.to
        )
        if not allowed:
            raise AclDenied(
                from_agent=msg.from_agent,
                to_agent=msg.to,
                reason=reason,
                roles_checked=roles_checked,
            )

    def get_roles_for_agent(self, agent: str) -> set[str]:
        """Get all roles assigned to an agent (supports multiple roles)."""
        roles = self._agent_roles.get_roles(agent)
        if not roles and "*" in self._agent_roles.get_roles("*"):
            roles = self._agent_roles.get_roles("*")
        return roles

    def set_role(self, agent: str, role_name: str) -> None:
        """
        Dynamically assign a role to an agent at runtime.

        Removes any existing role assignments for this agent from the
        in-memory mapping (does not modify the source config).
        """
        if role_name not in self._roles:
            raise ValueError(f"Unknown role: {role_name}")

        self._agent_roles.remove_agent(agent)
        self._agent_roles.add(agent, role_name)

    def swap_config(self, new_config: AclConfig) -> None:
        """
        Atomically hot-swap to a new AclConfig.

        This integrates with config hot-reload (HM-004) - accepts a fresh
        AclConfig and swaps it in, changing all decisions without restart.
        """
        self._config = new_config
        self._roles = {r.name: r for r in new_config.roles}
        self._default_policy = new_config.default_policy.lower()
        self._build_agent_role_map()

    @property
    def config(self) -> AclConfig:
        """Return the current ACL config."""
        return self._config

    @property
    def roles(self) -> tuple[AclRole, ...]:
        """Return all defined roles."""
        return self._config.roles

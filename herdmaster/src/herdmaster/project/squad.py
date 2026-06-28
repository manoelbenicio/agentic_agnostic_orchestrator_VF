"""Squad recommendation helpers for Project Mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SquadMember:
    """One recommended project squad member."""

    agent: str
    role: str
    rationale: str


class SquadRecommender:
    """Recommend idle agents and roles for FR-604."""

    def recommend(
        self,
        agents: list[dict[str, Any]],
        *,
        complexity_tier: str = "M",
        max_size: int | None = None,
    ) -> list[dict[str, str]]:
        """Return [{agent, role, rationale}, ...] from available agent metrics."""

        healthy = [
            agent for agent in agents
            if str(agent.get("health") or "healthy") == "healthy"
            and str(agent.get("role") or "") != "orchestrator"
        ]
        idle = [agent for agent in healthy if str(agent.get("state") or "") == "idle"]
        pool = idle or healthy or agents
        size = max_size or _default_size(complexity_tier)
        ranked = sorted(pool, key=_agent_rank)
        selected = ranked[: max(1, min(size, len(ranked)))] if ranked else []
        roles = _roles_for_count(len(selected))
        return [
            {
                "agent": str(agent.get("id")),
                "role": roles[index],
                "rationale": _rationale(agent),
            }
            for index, agent in enumerate(selected)
            if agent.get("id") is not None
        ]


def _default_size(complexity_tier: str) -> int:
    return {"S": 2, "M": 3, "L": 5, "XL": 7}.get(str(complexity_tier).upper(), 3)


def _roles_for_count(count: int) -> list[str]:
    if count <= 0:
        return []
    if count == 1:
        return ["lead_implementer"]
    if count == 2:
        return ["lead_implementer", "reviewer"]
    return ["lead_implementer", *["implementer" for _ in range(count - 2)], "reviewer"]


def _agent_rank(agent: dict[str, Any]) -> tuple[int, int, str]:
    state_penalty = 0 if str(agent.get("state") or "") == "idle" else 1
    avg_seconds = int(agent.get("avg_task_seconds") or 1800)
    return (state_penalty, avg_seconds, str(agent.get("id") or ""))


def _rationale(agent: dict[str, Any]) -> str:
    strengths = agent.get("strengths") or []
    if isinstance(strengths, list) and strengths:
        strength_text = ", ".join(str(item) for item in strengths)
    else:
        strength_text = str(agent.get("type") or "general execution")
    state = str(agent.get("state") or "unknown")
    return f"{state} agent with strengths in {strength_text}."

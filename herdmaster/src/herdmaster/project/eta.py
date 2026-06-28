"""ETA calculation for Project Mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


COMPLEXITY_MULTIPLIERS: dict[str, float] = {
    "S": 0.8,
    "M": 1.0,
    "L": 1.3,
    "XL": 1.8,
}


@dataclass(frozen=True, slots=True)
class EtaEstimate:
    """Three-point ETA estimate in hours."""

    optimistic_hours: float
    expected_hours: float
    pessimistic_hours: float
    rationale: str
    critical_path_depth: int
    parallelism_factor: int
    avg_task_time_hours: float
    complexity_multiplier: float


class EtaEstimator:
    """Compute the high-level Project Mode ETA from PRD section 6.6.5."""

    def estimate(
        self,
        tasks: list[dict[str, Any]],
        squad: list[dict[str, Any]],
        agents: list[dict[str, Any]],
        complexity_tier: str,
    ) -> EtaEstimate:
        """Return optimistic, expected, and pessimistic ETA values.

        Formula:
        critical_path_depth = longest_dependency_chain(tasks)
        parallelism_factor = min(agents, max_independent)
        avg_task_time = weighted_avg(type_times)
        multiplier = {S:0.8,M:1.0,L:1.3,XL:1.8}
        eta = (depth * avg * multiplier) / parallelism
        """

        normalized_tasks = [_normalize_task(task, index) for index, task in enumerate(tasks)]
        depth = max(1, critical_path_depth(normalized_tasks))
        max_independent = max(1, max_independent_tasks(normalized_tasks))
        available_agents = max(1, len(_squad_agent_ids(squad)) or len(agents))
        parallelism = max(1, min(available_agents, max_independent))
        avg_task_time = weighted_avg_task_time_hours(normalized_tasks, squad, agents)
        multiplier = COMPLEXITY_MULTIPLIERS.get(str(complexity_tier or "M").upper(), 1.0)
        expected = (depth * avg_task_time * multiplier) / parallelism
        expected = max(expected, 0.01)
        optimistic = expected * 0.75
        pessimistic = expected * 1.5
        rationale = (
            f"{len(normalized_tasks)} tasks, critical path depth {depth}, "
            f"parallelism {parallelism}, avg task time {avg_task_time:.2f}h, "
            f"complexity {str(complexity_tier or 'M').upper()} multiplier {multiplier:.1f}."
        )
        return EtaEstimate(
            optimistic_hours=round(optimistic, 2),
            expected_hours=round(expected, 2),
            pessimistic_hours=round(pessimistic, 2),
            rationale=rationale,
            critical_path_depth=depth,
            parallelism_factor=parallelism,
            avg_task_time_hours=round(avg_task_time, 2),
            complexity_multiplier=multiplier,
        )


def critical_path_depth(tasks: list[dict[str, Any]]) -> int:
    """Return the longest dependency chain length."""

    by_id = {str(task["id"]): task for task in tasks}
    by_title = {str(task.get("title") or task["id"]): task for task in tasks}
    memo: dict[str, int] = {}

    def depth(task: dict[str, Any], visiting: set[str]) -> int:
        task_id = str(task["id"])
        if task_id in memo:
            return memo[task_id]
        if task_id in visiting:
            return 1
        visiting.add(task_id)
        dependency_depths = []
        for dependency in _dependency_keys(task):
            parent = by_id.get(dependency) or by_title.get(dependency)
            if parent is not None:
                dependency_depths.append(depth(parent, visiting))
        visiting.remove(task_id)
        memo[task_id] = 1 + (max(dependency_depths) if dependency_depths else 0)
        return memo[task_id]

    return max((depth(task, set()) for task in tasks), default=0)


def max_independent_tasks(tasks: list[dict[str, Any]]) -> int:
    """Return the largest count of tasks at the same dependency depth."""

    by_id = {str(task["id"]): task for task in tasks}
    by_title = {str(task.get("title") or task["id"]): task for task in tasks}
    levels: dict[str, int] = {}

    def level(task: dict[str, Any], visiting: set[str]) -> int:
        task_id = str(task["id"])
        if task_id in levels:
            return levels[task_id]
        if task_id in visiting:
            return 0
        visiting.add(task_id)
        parent_levels = []
        for dependency in _dependency_keys(task):
            parent = by_id.get(dependency) or by_title.get(dependency)
            if parent is not None:
                parent_levels.append(level(parent, visiting))
        visiting.remove(task_id)
        levels[task_id] = 1 + (max(parent_levels) if parent_levels else 0)
        return levels[task_id]

    counts: dict[int, int] = {}
    for task in tasks:
        task_level = level(task, set())
        counts[task_level] = counts.get(task_level, 0) + 1
    return max(counts.values(), default=0)


def weighted_avg_task_time_hours(
    tasks: list[dict[str, Any]],
    squad: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> float:
    """Return weighted average task time in hours from assigned agent type metrics."""

    agent_by_id = {str(agent.get("id")): agent for agent in agents if agent.get("id") is not None}
    squad_agent_ids = _squad_agent_ids(squad)
    fallback_agent_ids = squad_agent_ids or list(agent_by_id)
    durations: list[float] = []

    for task in tasks:
        assigned_to = str(task.get("assigned_to") or task.get("agent") or "")
        candidates = [assigned_to] if assigned_to else fallback_agent_ids
        for agent_id in candidates:
            agent = agent_by_id.get(agent_id)
            if agent is None:
                continue
            seconds = agent.get("avg_task_seconds")
            if seconds is not None:
                durations.append(max(float(seconds) / 3600.0, 0.01))
                break

    if durations:
        return sum(durations) / len(durations)
    return 0.5


def _squad_agent_ids(squad: list[dict[str, Any]]) -> list[str]:
    return [str(item["agent"]) for item in squad if item.get("agent")]


def _normalize_task(task: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = dict(task)
    normalized.setdefault("id", str(task.get("key") or task.get("title") or f"task-{index + 1}"))
    return normalized


def _dependency_keys(task: dict[str, Any]) -> list[str]:
    depends_on = task.get("depends_on") or task.get("dependencies") or []
    if isinstance(depends_on, str):
        return [depends_on] if depends_on else []
    if isinstance(depends_on, list):
        return [str(value) for value in depends_on if value is not None]
    return []

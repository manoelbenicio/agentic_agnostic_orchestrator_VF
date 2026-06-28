"""Project Mode planner and approval workflow."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any

from herdmaster.config import HerdMasterConfig
from herdmaster.db.repositories import AgentRepo, ProjectRepo, TaskRepo
from herdmaster.dispatch.injector import DispatchInjector
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.herdr.adapter import HerdrAdapter

from .eta import EtaEstimator
from .squad import SquadRecommender


PROJECT_TEMPLATES: dict[str, str] = {
    "feature": "Implement a new user-facing capability with tests and documentation.",
    "bugfix": "Diagnose, fix, and verify a reported defect with regression coverage.",
    "refactor": "Improve internal structure without changing external behavior.",
    "migration": "Move data, APIs, or runtime behavior to a new target safely.",
}


@dataclass(frozen=True, slots=True)
class ProjectApprovalResult:
    """Result returned after project approval enqueues child tasks."""

    project: dict[str, Any]
    task_ids: list[str]


class ProjectPlanner:
    """High-level Project Mode workflow for FR-601 through FR-612."""

    def __init__(
        self,
        projects: ProjectRepo,
        tasks: TaskRepo,
        agents: AgentRepo,
        queue: TaskQueue,
        injector: DispatchInjector,
        adapter: HerdrAdapter,
        config: HerdMasterConfig | None = None,
    ) -> None:
        self.projects = projects
        self.tasks = tasks
        self.agents = agents
        self.queue = queue
        self.injector = injector
        self.adapter = adapter
        self.config = config
        self.eta = EtaEstimator()
        self.squad = SquadRecommender()

    async def create_project(
        self,
        name: str,
        full_scope_prompt: str,
        *,
        deadline: str | None = None,
        created_by: str | None = None,
        template: str | None = None,
        orchestrator_id: str | None = None,
        orchestrator_output: str | None = None,
    ) -> dict[str, Any]:
        """Create, analyze, and store a project awaiting human approval."""

        scope = _apply_template(full_scope_prompt, template)
        project_id = self.projects.create(name, scope, deadline=deadline, created_by=created_by)
        self.projects.update_state(project_id, "analyzing")
        prompt = self.build_analysis_prompt(project_id, name, scope, deadline=deadline)
        output = orchestrator_output
        if output is None:
            output = await self._inject_and_read_analysis(prompt, orchestrator_id=orchestrator_id)
        analysis = parse_orchestrator_analysis(output)
        agents = self.agents.list()
        if not analysis["squad"]:
            analysis["squad"] = self.squad.recommend(
                agents,
                complexity_tier=str(analysis.get("complexity_tier") or "M"),
            )
        estimate = self.eta.estimate(
            list(analysis.get("tasks") or []),
            list(analysis.get("squad") or []),
            agents,
            str(analysis.get("complexity_tier") or "M"),
        )
        analysis["eta_hours"] = estimate.expected_hours
        analysis["eta_rationale"] = analysis.get("eta_rationale") or estimate.rationale
        analysis["eta"] = {
            "optimistic_hours": estimate.optimistic_hours,
            "expected_hours": estimate.expected_hours,
            "pessimistic_hours": estimate.pessimistic_hours,
            "rationale": estimate.rationale,
        }
        self.projects.set_analysis(
            project_id,
            analysis,
            complexity_tier=str(analysis.get("complexity_tier") or "M"),
            squad_recommendation=analysis.get("squad") or [],
        )
        self.projects.set_eta(
            project_id,
            optimistic_hours=estimate.optimistic_hours,
            expected_hours=estimate.expected_hours,
            pessimistic_hours=estimate.pessimistic_hours,
            rationale=estimate.rationale,
        )
        self.projects.update_state(project_id, "awaiting_approval")
        project = self.projects.get(project_id)
        if project is None:
            raise KeyError(project_id)
        return project

    async def submit_project(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Alias for API callers that use PRD language."""

        return await self.create_project(*args, **kwargs)

    def build_analysis_prompt(
        self,
        project_id: str,
        name: str,
        full_scope_text: str,
        *,
        deadline: str | None = None,
    ) -> str:
        """Build the section 6.6.4 orchestrator analysis prompt."""

        agents = self.agents.list()
        metrics = _historical_metrics(self.projects, agents)
        agent_lines = "\n".join(_agent_line(agent) for agent in agents) or "- No registered agents"
        metric_lines = "\n".join(f"- {item}" for item in metrics) or "- No historical metrics yet"
        deadline_text = deadline or "none"
        return (
            "You are the Tech Lead orchestrator. Analyze the following project scope "
            "and produce a structured plan.\n\n"
            f"PROJECT ID:\n{project_id}\n\n"
            f"PROJECT NAME:\n{name}\n\n"
            f"DEADLINE:\n{deadline_text}\n\n"
            f"PROJECT SCOPE:\n{full_scope_text}\n\n"
            f"AVAILABLE AGENTS:\n{agent_lines}\n\n"
            f"HISTORICAL METRICS:\n{metric_lines}\n\n"
            "Produce your response in EXACTLY this JSON format:\n"
            "{\n"
            '  "complexity_tier": "S|M|L|XL",\n'
            '  "squad": [\n'
            '    {"agent": "A2", "role": "implementer", "rationale": "..."},\n'
            '    {"agent": "A4", "role": "lead_implementer", "rationale": "..."},\n'
            '    {"agent": "A6", "role": "reviewer", "rationale": "..."}\n'
            "  ],\n"
            '  "eta_hours": 2.5,\n'
            '  "eta_rationale": "12 tasks, 3 agents, avg 25 min/task, with parallelism...",\n'
            '  "tasks": [\n'
            '    {"title": "...", "description": "...", "prompt": "...", '
            '"assigned_to": "A2", "depends_on": [], "priority": "high"}\n'
            "  ]\n"
            "}\n"
        )

    def approve_project(
        self,
        project_id: str,
        *,
        decision: str = "accept",
        squad: list[dict[str, Any]] | None = None,
        eta: dict[str, Any] | None = None,
        assignments: list[dict[str, Any]] | None = None,
        human_notes: str | None = None,
    ) -> ProjectApprovalResult:
        """Accept, modify, or override the analyzed project and enqueue tasks."""

        project = _required_project(self.projects, project_id)
        if str(project.get("state")) != "awaiting_approval":
            raise ValueError(f"project {project_id!r} must be awaiting_approval")
        normalized_decision = decision.lower()
        if normalized_decision not in {"accept", "modify", "override"}:
            raise ValueError("decision must be accept, modify, or override")
        analysis = _analysis(project)
        final_squad = squad if squad is not None else list(analysis.get("squad") or [])
        task_specs = assignments if normalized_decision == "override" and assignments is not None else list(analysis.get("tasks") or [])
        if not task_specs:
            raise ValueError("approved project has no task breakdown")
        if normalized_decision == "modify" and assignments is not None:
            task_specs = assignments
        if eta is not None:
            self.projects.set_eta(
                project_id,
                optimistic_hours=_float_or_none(eta.get("optimistic_hours")),
                expected_hours=_float_or_none(eta.get("expected_hours") or eta.get("eta_hours")),
                pessimistic_hours=_float_or_none(eta.get("pessimistic_hours")),
                rationale=str(eta.get("rationale") or eta.get("eta_rationale") or ""),
            )
        self.projects.set_squad(
            project_id,
            final_squad,
            human_decision=normalized_decision,
            human_notes=human_notes,
            approved=True,
        )
        self.projects.update_state(project_id, "approved")
        task_ids = self._enqueue_project_tasks(project_id, task_specs)
        self.projects.update_progress(project_id)
        self.projects.update_state(project_id, "in_progress")
        updated = _required_project(self.projects, project_id)
        return ProjectApprovalResult(project=updated, task_ids=task_ids)

    def progress(self, project_id: str) -> dict[str, Any]:
        """Recompute and return project progress for FR-610."""

        self.projects.update_progress(project_id)
        project = _required_project(self.projects, project_id)
        total = int(project.get("total_tasks") or 0)
        completed = int(project.get("completed_tasks") or 0)
        failed = int(project.get("failed_tasks") or 0)
        percent = (completed / total * 100.0) if total else 0.0
        project["progress_pct"] = round(percent, 2)
        project["open_tasks"] = max(total - completed - failed, 0)
        if str(project.get("state")) == "completed":
            self.record_history(project_id)
        return project

    def record_history(self, project_id: str) -> int | None:
        """Persist completed project metrics for FR-612 once."""

        project = _required_project(self.projects, project_id)
        if str(project.get("state")) != "completed":
            return None
        existing = self.projects.conn.execute(
            "SELECT id FROM project_history WHERE project_id = ? LIMIT 1",
            (project_id,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        total_tasks = int(project.get("total_tasks") or 0)
        agents_used = len({
            str(task.get("assigned_to"))
            for task in self.tasks.list(project_id=project_id)
            if task.get("assigned_to")
        })
        estimated = _float_or_none(project.get("eta_expected_hours"))
        actual = _actual_hours(project)
        accuracy = _accuracy_pct(estimated, actual)
        return self.projects.insert_history(
            project_id,
            complexity_tier=str(project.get("complexity_tier") or ""),
            total_tasks=total_tasks,
            agents_used=agents_used,
            estimated_hours=estimated,
            actual_hours=actual,
            accuracy_pct=accuracy,
        )

    async def resolve_blocked_task(self, task_id: str, orchestrator_id: str | None = None) -> None:
        """Consult the Orchestrator to resolve a blocked task and unblock the worker."""
        task = self.tasks.get(task_id)
        if not task or task.get("state") != "blocked":
            return
            
        reason = str(task.get("blocked_reason") or "No reason provided")
        project_id = task.get("project_id")
        project_context = ""
        if project_id:
            project = self.projects.get(str(project_id))
            if project:
                project_context = f"\n\nPROJECT SCOPE:\n{project.get('scope')}"
                
        prompt = (
            "You are the Tech Lead orchestrator. One of your worker agents is blocked and needs "
            "your technical decision. You MUST review the documentation and provide a clear, "
            "data-driven directive.\n\n"
            f"BLOCKED TASK:\n{task.get('title')}\n{task.get('prompt')}\n\n"
            f"WORKER'S QUESTION/REASON:\n{reason}"
            f"{project_context}\n\n"
            "Produce your response in EXACTLY this JSON format:\n"
            "{\n"
            '  "directive": "The exact message/directive to send to the worker to unblock them."\n'
            "}\n"
        )
        
        output = await self._inject_and_read_analysis(prompt, orchestrator_id=orchestrator_id)
        payload = _extract_json_object(output)
        directive = payload.get("directive", "Resume work.")
        
        # Inject back into the worker's pane
        assigned_to = str(task.get("assigned_to"))
        if assigned_to:
            pane_id = await self._pane_for_agent(assigned_to)
            await self.adapter.pane_send(pane_id, f"\n[ORCHESTRATOR OVERRIDE]: {directive}\n")
        
        # Unblock task
        self.tasks.update_state(task_id, "in_progress")

    def _enqueue_project_tasks(self, project_id: str, task_specs: list[dict[str, Any]]) -> list[str]:
        normalized = [_normalize_task_spec(task, index) for index, task in enumerate(task_specs)]
        ordered = _topological_order(normalized)
        created: dict[str, str] = {}
        created_ids: list[str] = []
        for task in ordered:
            dependencies = [
                created[dependency]
                for dependency in _dependency_keys(task)
                if dependency in created
            ]
            task_id = self.queue.enqueue(
                str(task["title"]),
                str(task["prompt"]),
                project_id=project_id,
                description=str(task.get("description") or ""),
                priority=task.get("priority") or "normal",
                assigned_to=str(task.get("assigned_to") or "") or None,
                depends_on=dependencies,
                created_by=None,
            )
            created[str(task["key"])] = task_id
            created[str(task["title"])] = task_id
            created_ids.append(task_id)
        return created_ids

    async def _inject_and_read_analysis(
        self,
        prompt: str,
        *,
        orchestrator_id: str | None = None,
    ) -> str:
        orchestrator = orchestrator_id or _orchestrator_id(self.agents.list())
        analysis_task_id = self.queue.enqueue(
            "Analyze project scope",
            prompt,
            priority="critical",
            assigned_to=orchestrator,
            created_by=orchestrator,
            timeout_seconds=3600,
        )
        analysis_task = self.tasks.get(analysis_task_id)
        if analysis_task is None:
            raise KeyError(analysis_task_id)
        version = int(analysis_task.get("version") or 1)
        self.tasks.claim(analysis_task_id, orchestrator, version)
        assigned = self.tasks.get(analysis_task_id)
        if assigned is None:
            raise KeyError(analysis_task_id)
        await self.injector.dispatch(assigned)
        pane_id = await self._pane_for_agent(orchestrator)
        
        # Fallback to robust polling: Wait for the agent to finish thinking and output JSON
        attempts = 0
        max_attempts = 360 # 360 * 5s = 30 minutes timeout
        last_clean_text = ""
        while attempts < max_attempts:
            await asyncio.sleep(5.0)
            attempts += 1
            text = await self.adapter.pane_read(pane_id)
            try:
                # If we can parse a JSON from the current terminal text, it's done!
                _extract_json_object(text)
                return text
            except ValueError as e:
                # Still generating or haven't started. Keep polling.
                last_clean_text = str(e)
                pass
                
        raise TimeoutError(f"Agent took too long to output JSON. Last buffer: {last_clean_text}")

    async def _pane_for_agent(self, agent_id: str) -> str:
        stored = self.agents.get(agent_id)
        if stored is not None and stored.get("herdr_pane"):
            return str(stored["herdr_pane"])
        for agent in await self.adapter.agent_list():
            if agent.id == agent_id and agent.pane_id:
                return agent.pane_id
        raise ValueError(f"orchestrator {agent_id!r} has no Herdr pane")


def parse_orchestrator_analysis(text: str) -> dict[str, Any]:
    """Parse orchestrator JSON even when surrounded by prose."""

    payload = _extract_json_object(text)
    if not isinstance(payload, dict):
        raise ValueError("orchestrator analysis must be a JSON object")
    complexity = str(payload.get("complexity_tier") or "M").upper()
    if complexity not in {"S", "M", "L", "XL"}:
        complexity = "M"
    squad = payload.get("squad") if isinstance(payload.get("squad"), list) else []
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
    return {
        "complexity_tier": complexity,
        "squad": [_normalize_squad_member(item) for item in squad if isinstance(item, dict)],
        "eta_hours": _float_or_none(payload.get("eta_hours")),
        "eta_rationale": str(payload.get("eta_rationale") or ""),
        "tasks": [_normalize_task_spec(item, index) for index, item in enumerate(tasks) if isinstance(item, dict)],
        "raw": payload,
    }


def _extract_json_object(text: str) -> Any:
    # Remove hidden ANSI escape sequences from terminal capture
    ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    clean_text = ansi_escape.sub('', text)
    
    # Unwrap terminal line breaks and spaces
    clean_text = clean_text.replace('\n  ', '')
    clean_text = clean_text.replace('\r', '')
    clean_text = clean_text.replace('\n', '')

    decoder = json.JSONDecoder()
    stripped = clean_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stripped[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError(f"no JSON object found in orchestrator output. Cleaned text preview: {clean_text[:200]}")


def _normalize_squad_member(item: dict[str, Any]) -> dict[str, str]:
    return {
        "agent": str(item.get("agent") or item.get("agent_id") or ""),
        "role": str(item.get("role") or "implementer"),
        "rationale": str(item.get("rationale") or ""),
    }


def _normalize_task_spec(task: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(task.get("title") or f"Project task {index + 1}")
    description = str(task.get("description") or "")
    prompt = str(task.get("prompt") or description or title)
    key = str(task.get("id") or task.get("key") or title)
    priority = str(task.get("priority") or "normal").lower()
    if priority == "medium":
        priority = "normal"
    
    return {
        "key": key,
        "title": title,
        "description": description,
        "prompt": prompt,
        "assigned_to": str(task.get("assigned_to") or task.get("agent") or ""),
        "depends_on": _dependency_keys(task),
        "priority": priority,
    }


def _topological_order(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {str(task["key"]): task for task in tasks}
    by_title = {str(task["title"]): task for task in tasks}
    ordered: list[dict[str, Any]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task: dict[str, Any]) -> None:
        key = str(task["key"])
        if key in visited:
            return
        if key in visiting:
            return
        visiting.add(key)
        for dependency in _dependency_keys(task):
            parent = by_key.get(dependency) or by_title.get(dependency)
            if parent is not None:
                visit(parent)
        visiting.remove(key)
        visited.add(key)
        ordered.append(task)

    for task in tasks:
        visit(task)
    return ordered


def _dependency_keys(task: dict[str, Any]) -> list[str]:
    depends_on = task.get("depends_on") or task.get("dependencies") or []
    if isinstance(depends_on, str):
        return [depends_on] if depends_on else []
    if isinstance(depends_on, list):
        return [str(value) for value in depends_on if value is not None]
    return []


def _required_project(projects: ProjectRepo, project_id: str) -> dict[str, Any]:
    project = projects.get(project_id)
    if project is None:
        raise KeyError(project_id)
    return project


def _analysis(project: dict[str, Any]) -> dict[str, Any]:
    analysis = project.get("orchestrator_analysis")
    if isinstance(analysis, dict):
        return analysis
    return {}


def _orchestrator_id(agents: list[dict[str, Any]]) -> str:
    for agent in agents:
        if str(agent.get("role") or "") == "orchestrator" and agent.get("id"):
            return str(agent["id"])
    for agent in agents:
        if str(agent.get("id") or "") == "A1":
            return "A1"
    if agents and agents[0].get("id"):
        return str(agents[0]["id"])
    raise ValueError("no agents available for orchestrator analysis")


def _agent_line(agent: dict[str, Any]) -> str:
    strengths = agent.get("strengths") or []
    if isinstance(strengths, list) and strengths:
        strength_text = ", ".join(str(item) for item in strengths)
    else:
        strength_text = str(agent.get("type") or "general")
    state = str(agent.get("state") or "unknown")
    avg_seconds = agent.get("avg_task_seconds")
    eta_text = "idle now" if state == "idle" else "availability unknown"
    if avg_seconds is not None:
        eta_text = f"avg task {int(avg_seconds) // 60} min"
    return f"- {agent.get('id')}: {agent.get('type')} ({state}) - strengths: {strength_text}; {eta_text}"


def _historical_metrics(projects: ProjectRepo, agents: list[dict[str, Any]]) -> list[str]:
    metrics: list[str] = []
    type_seconds: dict[str, list[int]] = {}
    for agent in agents:
        if agent.get("avg_task_seconds") is None:
            continue
        agent_type = str(agent.get("type") or "unknown")
        type_seconds.setdefault(agent_type, []).append(int(agent["avg_task_seconds"]))
    for agent_type, values in sorted(type_seconds.items()):
        avg_minutes = round((sum(values) / len(values)) / 60)
        metrics.append(f"Avg task completion ({agent_type}): {avg_minutes} min")
    for tier in ("S", "M", "L", "XL"):
        history = projects.complexity_lookup(tier)
        if history:
            avg_tasks = sum(int(row.get("total_tasks") or 0) for row in history) / len(history)
            metrics.append(f"Avg tasks per {tier} project: {avg_tasks:.1f}")
    return metrics


def _apply_template(scope: str, template: str | None) -> str:
    if template is None:
        return scope
    normalized = template.lower()
    if normalized not in PROJECT_TEMPLATES:
        raise ValueError(f"unknown project template {template!r}")
    return f"{PROJECT_TEMPLATES[normalized]}\n\n{scope}"


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _actual_hours(project: dict[str, Any]) -> float | None:
    created = _parse_time(project.get("created_at"))
    completed = _parse_time(project.get("completed_at"))
    if created is None or completed is None:
        return None
    return max((completed - created).total_seconds() / 3600.0, 0.0)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _accuracy_pct(estimated: float | None, actual: float | None) -> float | None:
    if estimated is None or actual is None or actual == 0:
        return None
    error = abs(estimated - actual) / actual
    return round(max(0.0, 100.0 * (1.0 - error)), 2)

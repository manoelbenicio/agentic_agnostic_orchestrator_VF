from __future__ import annotations

import json

import pytest

from herdmaster.dispatch.queue import TaskQueue
from herdmaster.project.eta import (
    COMPLEXITY_MULTIPLIERS,
    EtaEstimator,
    critical_path_depth,
    max_independent_tasks,
    weighted_avg_task_time_hours,
)
from herdmaster.project.planner import ProjectPlanner, parse_orchestrator_analysis
from herdmaster.project.squad import SquadMember, SquadRecommender


class DummyInjector:
    def __init__(self):
        self.dispatched = []

    async def dispatch(self, task):
        self.dispatched.append(task)


def _planner(repos, mock_herdr_adapter, test_config):
    return ProjectPlanner(
        repos.projects,
        repos.tasks,
        repos.agents,
        TaskQueue(repos.tasks, repos.agents),
        DummyInjector(),
        mock_herdr_adapter,
        test_config,
    )


def _analysis_output(*, tasks=None, squad=None, complexity="M"):
    return json.dumps(
        {
            "complexity_tier": complexity,
            "squad": squad
            if squad is not None
            else [
                {"agent": "A2", "role": "lead_implementer", "rationale": "fast"},
                {"agent": "A3", "role": "reviewer", "rationale": "tests"},
            ],
            "eta_hours": 99,
            "eta_rationale": "orchestrator estimate",
            "tasks": tasks
            if tasks is not None
            else [
                {"id": "schema", "title": "Schema", "prompt": "Build schema", "assigned_to": "A2", "priority": "critical"},
                {"id": "api", "title": "API", "prompt": "Build API", "assigned_to": "A3", "depends_on": ["schema"], "priority": "high"},
            ],
        }
    )


def test_eta_formula_exactness_on_known_dag():
    tasks = [
        {"id": "A", "title": "A", "assigned_to": "A2"},
        {"id": "B", "title": "B", "assigned_to": "A3", "depends_on": ["A"]},
        {"id": "C", "title": "C", "assigned_to": "A2", "depends_on": ["B"]},
        {"id": "D", "title": "D", "assigned_to": "A3", "depends_on": ["A"]},
    ]
    agents = [
        {"id": "A2", "avg_task_seconds": 1800},
        {"id": "A3", "avg_task_seconds": 3600},
    ]
    squad = [{"agent": "A2"}, {"agent": "A3"}]

    assert COMPLEXITY_MULTIPLIERS == {"S": 0.8, "M": 1.0, "L": 1.3, "XL": 1.8}
    assert critical_path_depth(tasks) == 3
    assert max_independent_tasks(tasks) == 2
    assert weighted_avg_task_time_hours(tasks, squad, agents) == pytest.approx(0.75)

    estimate = EtaEstimator().estimate(tasks, squad, agents, "L")

    # eta = (critical path depth 3 * avg task time .75h * L multiplier 1.3) / parallelism 2
    assert estimate.critical_path_depth == 3
    assert estimate.parallelism_factor == 2
    assert estimate.avg_task_time_hours == 0.75
    assert estimate.complexity_multiplier == 1.3
    assert estimate.expected_hours == 1.46
    assert estimate.optimistic_hours == 1.1
    assert estimate.pessimistic_hours == 2.19
    assert estimate.optimistic_hours <= estimate.expected_hours <= estimate.pessimistic_hours


def test_eta_uses_each_complexity_multiplier():
    tasks = [{"id": "A", "assigned_to": "A2"}]
    agents = [{"id": "A2", "avg_task_seconds": 3600}]
    squad = [{"agent": "A2"}]

    estimates = {
        tier: EtaEstimator().estimate(tasks, squad, agents, tier).expected_hours
        for tier in ("S", "M", "L", "XL")
    }

    assert estimates == {"S": 0.8, "M": 1.0, "L": 1.3, "XL": 1.8}


def test_squad_recommender_prefers_idle_healthy_non_orchestrator_agents():
    agents = [
        {"id": "A1", "role": "orchestrator", "state": "idle", "health": "healthy", "avg_task_seconds": 1},
        {"id": "A2", "role": "worker", "state": "working", "health": "healthy", "avg_task_seconds": 10},
        {"id": "A3", "role": "worker", "state": "idle", "health": "healthy", "avg_task_seconds": 1200, "strengths": ["tests"]},
        {"id": "A4", "role": "worker", "state": "idle", "health": "healthy", "avg_task_seconds": 900, "strengths": ["api"]},
        {"id": "A5", "role": "worker", "state": "idle", "health": "unhealthy", "avg_task_seconds": 100},
    ]

    squad = SquadRecommender().recommend(agents, complexity_tier="M")

    assert SquadMember("A4", "lead_implementer", "idle agent with strengths in api.")
    assert [member["agent"] for member in squad] == ["A4", "A3"]
    assert [member["role"] for member in squad] == ["lead_implementer", "reviewer"]
    assert all("idle agent" in member["rationale"] for member in squad)


def test_parse_orchestrator_analysis_handles_json_in_prose_and_bad_output():
    text = """
    I analyzed the work. Here is the structured plan:
    {
      "complexity_tier": "XL",
      "squad": [{"agent_id": "A2", "role": "reviewer", "rationale": "strong tests"}],
      "eta_hours": "4.5",
      "tasks": [{"title": "Only title", "description": "Do it"}]
    }
    Thanks.
    """

    parsed = parse_orchestrator_analysis(text)

    assert parsed["complexity_tier"] == "XL"
    assert parsed["eta_hours"] == 4.5
    assert parsed["squad"] == [{"agent": "A2", "role": "reviewer", "rationale": "strong tests"}]
    assert parsed["tasks"] == [
        {
            "key": "Only title",
            "title": "Only title",
            "description": "Do it",
            "prompt": "Do it",
            "assigned_to": "",
            "depends_on": [],
            "priority": "normal",
        }
    ]

    with pytest.raises(ValueError, match="no JSON object found"):
        parse_orchestrator_analysis("no structured payload here")


@pytest.mark.asyncio
async def test_create_project_stores_analysis_and_moves_to_awaiting_approval(
    repos,
    make_agent,
    mock_herdr_adapter,
    test_config,
):
    make_agent("A1", role="orchestrator", state="idle")
    make_agent("A2", role="worker", state="idle")
    make_agent("A3", role="worker", state="idle")
    repos.agents.update_metrics("A2", 1800)
    repos.agents.update_metrics("A3", 3600)
    planner = _planner(repos, mock_herdr_adapter, test_config)

    project = await planner.create_project(
        "Project Mode",
        "Build Project Mode",
        deadline="2026-06-25T18:00:00Z",
        created_by="tester",
        orchestrator_output=_analysis_output(complexity="L"),
    )

    assert project["state"] == "awaiting_approval"
    assert project["complexity_tier"] == "L"
    assert project["deadline"] == "2026-06-25T18:00:00Z"
    assert project["orchestrator_analysis"]["tasks"][0]["key"] == "schema"
    assert project["squad_recommendation"][0]["agent"] == "A2"
    assert project["eta_expected_hours"] is not None
    assert project["eta_optimistic_hours"] <= project["eta_expected_hours"] <= project["eta_pessimistic_hours"]


@pytest.mark.asyncio
async def test_approve_decomposes_tasks_in_dependency_order_with_project_id_and_null_creator(
    repos,
    make_agent,
    mock_herdr_adapter,
    test_config,
):
    make_agent("A1", role="orchestrator", state="idle")
    make_agent("A2", role="worker", state="idle")
    make_agent("A3", role="worker", state="idle")
    planner = _planner(repos, mock_herdr_adapter, test_config)
    tasks = [
        {"id": "tests", "title": "Tests", "prompt": "Write tests", "assigned_to": "A3", "depends_on": ["api"]},
        {"id": "schema", "title": "Schema", "prompt": "Build schema", "assigned_to": "A2", "priority": "critical"},
        {"id": "api", "title": "API", "prompt": "Build API", "assigned_to": "A2", "depends_on": ["schema"], "priority": "high"},
    ]
    project = await planner.create_project("Decompose", "Build it", orchestrator_output=_analysis_output(tasks=tasks))

    result = planner.approve_project(str(project["id"]))
    created = repos.tasks.list(project_id=str(project["id"]))

    assert result.project["state"] == "in_progress"
    assert result.task_ids == [task["id"] for task in created]
    assert [task["title"] for task in created] == ["Schema", "API", "Tests"]
    assert all(task["project_id"] == project["id"] for task in created)
    assert all(task["created_by"] is None for task in created)
    assert created[0]["depends_on"] == []
    assert created[1]["depends_on"] == [created[0]["id"]]
    assert created[2]["depends_on"] == [created[1]["id"]]
    assert created[0]["priority"] == 0
    assert created[1]["priority"] == 1
    assert created[2]["priority"] == 2


@pytest.mark.asyncio
async def test_analysis_task_created_by_orchestrator_when_injection_path_is_used(
    repos,
    make_agent,
    mock_herdr_adapter,
    test_config,
):
    make_agent("A1", role="orchestrator", state="idle", herdr_pane="pane-A1")
    make_agent("A2", role="worker", state="idle")
    make_agent("A3", role="worker", state="idle")
    mock_herdr_adapter.pane_outputs["pane-A1"] = [_analysis_output()]
    planner = _planner(repos, mock_herdr_adapter, test_config)

    project = await planner.create_project("Injected", "Analyze through pane", orchestrator_id="A1")
    analysis_tasks = repos.tasks.list(assigned_to="A1")

    assert project["state"] == "awaiting_approval"
    assert len(analysis_tasks) == 1
    assert analysis_tasks[0]["title"] == "Analyze project scope"
    assert analysis_tasks[0]["created_by"] == "A1"
    assert analysis_tasks[0]["state"] == "assigned"
    assert analysis_tasks[0]["priority"] == 0
    assert planner.injector.dispatched[0]["id"] == analysis_tasks[0]["id"]


@pytest.mark.asyncio
async def test_project_progress_records_history_once_after_all_tasks_done(
    repos,
    make_agent,
    mock_herdr_adapter,
    test_config,
):
    make_agent("A1", role="orchestrator", state="idle")
    make_agent("A2", role="worker", state="idle")
    make_agent("A3", role="worker", state="idle")
    planner = _planner(repos, mock_herdr_adapter, test_config)
    project = await planner.create_project("History", "Build it", orchestrator_output=_analysis_output(complexity="M"))
    result = planner.approve_project(str(project["id"]))

    for task_id in result.task_ids:
        repos.tasks.update_state(task_id, "done")

    progress = planner.progress(str(project["id"]))
    first_history_id = planner.record_history(str(project["id"]))
    second_history_id = planner.record_history(str(project["id"]))
    rows = repos.projects.conn.execute(
        "SELECT * FROM project_history WHERE project_id = ?",
        (project["id"],),
    ).fetchall()

    assert progress["state"] == "completed"
    assert progress["total_tasks"] == 2
    assert progress["completed_tasks"] == 2
    assert progress["failed_tasks"] == 0
    assert progress["progress_pct"] == 100.0
    assert progress["open_tasks"] == 0
    assert first_history_id == second_history_id
    assert len(rows) == 1
    assert rows[0]["complexity_tier"] == "M"
    assert rows[0]["total_tasks"] == 2
    assert rows[0]["agents_used"] == 2

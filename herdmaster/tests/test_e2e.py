"""End-to-end lifecycle tests for HerdMaster (HM-014-E2E).

These tests wire the *real* service objects together — :class:`TaskQueue`,
:class:`DispatchInjector`, :class:`ProjectPlanner`, :class:`WatchdogEngine`,
and the SQLite repositories — against a temporary database and a fully mocked
Herdr adapter (``conftest.MockHerdrAdapter``). No live Herdr process, no
subprocess, no sockets: everything is deterministic.

Covered PRD §15 scenarios:

* TC-001 — orchestrator creates a task, worker idle → task dispatched.
* TC-002 — worker busy → task requeued, dispatched once the worker is idle.
* TC-009 — project submitted → analyzed → squad + ETA produced.
* TC-010 — human modifies the squad recommendation → modified squad stored.
* TC-011 — project with a dependency chain → tasks enqueued/dispatched in
  dependency order; project completes and history is recorded (FR-612).
* TC-003 (spirit) — stuck agent → watchdog detects and recovers via the
  mocked adapter.

The tests treat the source as frozen: a real defect should surface as a test
failure to be reported, not patched here.
"""

from __future__ import annotations

import json

import pytest

from herdmaster.dispatch.injector import DispatchInjector, DispatchInjectorConfig
from herdmaster.dispatch.queue import TaskQueue
from herdmaster.herdr.adapter import HerdrError
from herdmaster.herdr.parser import HerdrAgent
from herdmaster.project.planner import ProjectPlanner
from herdmaster.watchdog.engine import WatchdogEngine


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class Clock:
    """Deterministic monotonic clock for the watchdog (mirrors test_watchdog)."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def set(self, value: float) -> None:
        self.value = value


class Replayer:
    """Records which agents had their last task replayed during recovery."""

    def __init__(self) -> None:
        self.agent_ids: list[str] = []

    async def replay_last_task(self, agent_id: str) -> None:
        self.agent_ids.append(agent_id)


def fast_injector(repos, adapter, tmp_path):
    """Build a DispatchInjector + TaskQueue with no real sleeps for fast tests."""

    queue = TaskQueue(repos.tasks, repos.agents)
    config = DispatchInjectorConfig(
        idle_timeout_s=1,
        max_chunk_chars=10_000,
        file_fallback_threshold_chars=1_000_000,
        chunk_pace_s=0.0,
        retry_attempts=3,
        base_backoff_s=0.0,
        max_backoff_s=0.0,
        fallback_dir=tmp_path / "prompts",
    )
    injector = DispatchInjector(adapter, queue, repos.agents, config)
    return queue, injector


def _orchestrator_stub(tasks: list[dict], *, squad: list[dict], tier: str = "M") -> str:
    """Return a stub orchestrator analysis JSON string (as a real model would emit)."""

    return json.dumps(
        {
            "complexity_tier": tier,
            "squad": squad,
            "eta_hours": 2.5,
            "eta_rationale": "stub estimate",
            "tasks": tasks,
        }
    )


# ---------------------------------------------------------------------------
# Task-only lifecycle (TC-001 / TC-002)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_only_lifecycle_idle_worker_dispatches_to_done(
    repos, make_agent, mock_herdr_adapter, tmp_path
):
    """TC-001: idle worker → create → claim → dispatch → in_progress → done."""

    make_agent("W1", state="idle", herdr_pane="pane-W1")
    queue, injector = fast_injector(repos, mock_herdr_adapter, tmp_path)

    # Orchestrator creates a standalone task; it lands queued.
    task_id = queue.enqueue("Build feature", "Implement the feature", priority="high")
    assert repos.tasks.get(task_id)["state"] == "queued"

    # Worker claims the next ready task (CAS) → assigned.
    claimed = await queue.claim_next("W1")
    assert claimed is not None
    assert claimed["id"] == task_id
    assert claimed["state"] == "assigned"
    assert claimed["assigned_to"] == "W1"

    # Idle-gated dispatch injects the prompt and advances to in_progress.
    result = await injector.dispatch(claimed)
    assert result.status == "in_progress"
    assert result.pane_id == "pane-W1"
    assert repos.tasks.get(task_id)["state"] == "in_progress"

    # The adapter was asked to confirm idle and to send the prompt.
    call_names = [name for name, _a, _k in mock_herdr_adapter.calls]
    assert "agent_wait" in call_names
    assert "pane_send" in call_names

    # Worker finishes the task.
    done = queue.mark_done(task_id, duration_seconds=42)
    assert done["state"] == "done"
    assert done["duration_seconds"] == 42


@pytest.mark.asyncio
async def test_task_only_lifecycle_busy_worker_requeues_then_dispatches(
    repos, make_agent, mock_herdr_adapter, tmp_path
):
    """TC-002: busy worker → task requeued, then dispatched once idle."""

    make_agent("W1", state="working", herdr_pane="pane-W1")
    queue, injector = fast_injector(repos, mock_herdr_adapter, tmp_path)

    task_id = queue.enqueue("Deferred task", "Do it when free")

    # First attempt: agent is not idle (adapter raises) → requeued for later.
    mock_herdr_adapter.wait_results = [HerdrError("agent still busy")]
    claimed = await queue.claim_next("W1")
    assert claimed is not None
    first = await injector.dispatch(claimed)
    assert first.status == "requeued"

    requeued = repos.tasks.get(task_id)
    assert requeued["state"] == "queued"
    assert requeued["assigned_to"] is None
    assert requeued["retry_count"] == 1

    # Second attempt: worker is idle now (no scripted failures) → dispatched.
    mock_herdr_adapter.wait_results = []
    claimed_again = await queue.claim_next("W1")
    assert claimed_again is not None
    second = await injector.dispatch(claimed_again)
    assert second.status == "in_progress"
    assert repos.tasks.get(task_id)["state"] == "in_progress"

    queue.mark_done(task_id, duration_seconds=10)
    assert repos.tasks.get(task_id)["state"] == "done"


# ---------------------------------------------------------------------------
# Project Mode lifecycle (TC-009 / TC-010 / TC-011)
# ---------------------------------------------------------------------------


def _build_planner(repos, adapter, tmp_path):
    queue, injector = fast_injector(repos, adapter, tmp_path)
    planner = ProjectPlanner(
        repos.projects,
        repos.tasks,
        repos.agents,
        queue,
        injector,
        adapter,
    )
    return planner, queue, injector


@pytest.mark.asyncio
async def test_project_analysis_produces_squad_and_eta(
    repos, make_agent, mock_herdr_adapter, tmp_path
):
    """TC-009: project submitted → analyzed → squad + ETA awaiting approval."""

    make_agent("A2", state="idle", herdr_pane="pane-A2", role="worker")
    make_agent("A4", state="idle", herdr_pane="pane-A4", role="worker")
    planner, _queue, _injector = _build_planner(repos, mock_herdr_adapter, tmp_path)

    stub = _orchestrator_stub(
        tasks=[
            {"title": "Schema", "prompt": "Design schema", "assigned_to": "A2", "priority": "critical"},
            {"title": "API", "prompt": "Build API", "assigned_to": "A4", "priority": "high", "depends_on": ["Schema"]},
        ],
        squad=[
            {"agent": "A2", "role": "implementer", "rationale": "fast"},
            {"agent": "A4", "role": "lead_implementer", "rationale": "auth"},
        ],
        tier="M",
    )

    project = await planner.create_project(
        "Auth System", "Build authentication", orchestrator_output=stub
    )

    assert project["state"] == "awaiting_approval"
    assert project["complexity_tier"] == "M"
    # Squad recommendation persisted (TC-009).
    assert [m["agent"] for m in project["squad_recommendation"]] == ["A2", "A4"]
    # Three-point ETA computed and stored.
    assert project["eta_expected_hours"] is not None
    assert project["eta_optimistic_hours"] <= project["eta_expected_hours"] <= project["eta_pessimistic_hours"]


@pytest.mark.asyncio
async def test_project_human_modifies_squad_then_dispatches(
    repos, make_agent, mock_herdr_adapter, tmp_path
):
    """TC-010: human modifies the squad recommendation → modified squad stored."""

    make_agent("A2", state="idle", herdr_pane="pane-A2", role="worker")
    make_agent("A4", state="idle", herdr_pane="pane-A4", role="worker")
    planner, _queue, _injector = _build_planner(repos, mock_herdr_adapter, tmp_path)

    stub = _orchestrator_stub(
        tasks=[{"title": "Task1", "prompt": "Do task 1", "assigned_to": "A2", "priority": "normal"}],
        squad=[{"agent": "A2", "role": "implementer", "rationale": "default"}],
    )
    project = await planner.create_project("Proj", "scope", orchestrator_output=stub)
    project_id = project["id"]

    modified_squad = [
        {"agent": "A4", "role": "lead_implementer", "rationale": "human override"},
        {"agent": "A2", "role": "reviewer", "rationale": "human override"},
    ]
    result = planner.approve_project(project_id, decision="modify", squad=modified_squad)

    assert result.task_ids  # tasks were enqueued
    updated = repos.projects.get(project_id)
    assert updated["state"] == "in_progress"
    assert updated["human_decision"] == "modify"
    assert [m["agent"] for m in updated["squad_approved"]] == ["A4", "A2"]


@pytest.mark.asyncio
async def test_project_dependency_order_completes_and_records_history(
    repos, make_agent, mock_herdr_adapter, tmp_path
):
    """TC-011: dependency chain dispatched in order; project completes; history written."""

    make_agent("W1", state="idle", herdr_pane="pane-W1", role="worker")
    planner, queue, injector = _build_planner(repos, mock_herdr_adapter, tmp_path)

    # Dependency chain depth 3: Schema → API → Tests.
    stub = _orchestrator_stub(
        tasks=[
            {"title": "Tests", "prompt": "Write tests", "priority": "normal", "depends_on": ["API"]},
            {"title": "API", "prompt": "Build API", "priority": "high", "depends_on": ["Schema"]},
            {"title": "Schema", "prompt": "Design schema", "priority": "critical"},
        ],
        squad=[{"agent": "W1", "role": "lead_implementer", "rationale": "solo"}],
        tier="L",
    )
    project = await planner.create_project("Chained", "scope", orchestrator_output=stub)
    project_id = project["id"]

    approval = planner.approve_project(project_id, decision="accept")
    task_ids = approval.task_ids
    assert len(task_ids) == 3

    # Tasks enqueued in topological order: Schema, API, Tests.
    titles_in_order = [repos.tasks.get(tid)["title"] for tid in task_ids]
    assert titles_in_order == ["Schema", "API", "Tests"]

    # The dependent tasks carry the resolved real id of their parent.
    by_title = {repos.tasks.get(tid)["title"]: repos.tasks.get(tid) for tid in task_ids}
    schema_id = by_title["Schema"]["id"]
    api_id = by_title["API"]["id"]
    assert by_title["API"]["depends_on"] == [schema_id]
    assert by_title["Tests"]["depends_on"] == [api_id]

    # Drain the queue honoring dependency gating: claim → dispatch → done.
    dispatch_order: list[str] = []
    while True:
        claimed = await queue.claim_next("W1")
        if claimed is None:
            break
        result = await injector.dispatch(claimed)
        assert result.status == "in_progress"
        dispatch_order.append(repos.tasks.get(claimed["id"])["title"])
        queue.mark_done(claimed["id"], duration_seconds=30)

    # Dependency order respected during dispatch (TC-011).
    assert dispatch_order == ["Schema", "API", "Tests"]

    # Project recomputes to completed and writes history (FR-612).
    completed = planner.progress(project_id)
    assert completed["state"] == "completed"
    assert int(completed["completed_tasks"]) == 3

    history = repos.projects.conn.execute(
        "SELECT project_id, total_tasks, agents_used FROM project_history WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    assert len(history) == 1
    assert history[0]["total_tasks"] == 3
    assert history[0]["agents_used"] == 1


# ---------------------------------------------------------------------------
# Watchdog recovery (TC-003 spirit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_detects_stuck_agent_and_recovers(
    temp_db, repos, make_agent, mock_herdr_adapter, test_config
):
    """TC-003 (spirit): a stuck working agent is detected and recovered via the adapter."""

    make_agent("A1", state="working", herdr_pane="pane-A1")
    mock_herdr_adapter.agents = [HerdrAgent("A1", "Codex", "codex", "working", "pane-A1", "ws")]
    mock_herdr_adapter.pane_outputs = {"pane-A1": ["stuck output"]}
    replayer = Replayer()
    clock = Clock(0)

    engine = WatchdogEngine(
        mock_herdr_adapter,
        repos.agents,
        test_config.watchdog,
        command_resolver=lambda agent_id, agent: "codex --resume",
        task_replayer=replayer,
        now=clock,
    )

    # First pass: healthy baseline.
    await engine.poll_once()
    assert repos.agents.get("A1")["health"] == "healthy"

    # Advance past the hard timeout with no progress → recovery kicks in.
    clock.set(11)
    await engine.poll_once()
    await engine._monitors["A1"].recovery_task

    call_names = [name for name, _a, _k in mock_herdr_adapter.calls]
    assert "pane_send" in call_names      # ctrl-c kill fallback
    assert "spawn_agent" in call_names    # respawn
    assert "agent_wait" in call_names     # wait for idle
    assert replayer.agent_ids == ["A1"]   # last task replayed
    assert repos.agents.get("A1")["health"] == "healthy"


@pytest.mark.asyncio
async def test_watchdog_idle_agent_stays_healthy(
    repos, make_agent, mock_herdr_adapter, test_config
):
    """A resting (idle) agent must never be flagged for recovery even after time passes."""

    make_agent("A1", state="unknown", herdr_pane="pane-A1")
    mock_herdr_adapter.agents = [HerdrAgent("A1", "Codex", "codex", "idle", "pane-A1", "ws")]
    mock_herdr_adapter.pane_outputs = {"pane-A1": ["idle prompt"]}
    clock = Clock(0)
    engine = WatchdogEngine(mock_herdr_adapter, repos.agents, test_config.watchdog, now=clock)

    await engine.poll_once()
    clock.set(100)
    await engine.poll_once()

    agent = repos.agents.get("A1")
    assert agent["state"] == "idle"
    assert agent["health"] == "healthy"

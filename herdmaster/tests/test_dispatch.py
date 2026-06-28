from __future__ import annotations

from pathlib import Path

import pytest

from herdmaster.dispatch.injector import DispatchInjector, DispatchInjectorConfig
from herdmaster.dispatch.queue import TaskQueue, TaskStateError
from herdmaster.herdr.adapter import HerdrError


def make_queue(repos):
    return TaskQueue(repos.tasks, repos.agents)


def injector_config(tmp_path: Path, **overrides):
    values = {
        "idle_timeout_s": 1,
        "max_chunk_chars": 10,
        "file_fallback_threshold_chars": 10_000,
        "chunk_pace_s": 0.0,
        "retry_attempts": 1,
        "base_backoff_s": 0.0,
        "max_backoff_s": 0.0,
        "fallback_dir": tmp_path / "prompts",
    }
    values.update(overrides)
    return DispatchInjectorConfig(**values)


async def assigned_task(queue: TaskQueue, make_agent, agent_id="A1", *, prompt="prompt", **enqueue_kwargs):
    make_agent(agent_id)
    task_id = queue.enqueue("dispatch me", prompt, **enqueue_kwargs)
    task = await queue.claim_next(agent_id)
    assert task is not None
    return task


def sent_texts(mock_herdr_adapter):
    return [args[1] for name, args, _kwargs in mock_herdr_adapter.calls if name == "pane_send"]


def test_task_queue_priority_ordering(repos, make_agent):
    make_agent("A1")
    queue = make_queue(repos)
    low = queue.enqueue("low", "low", priority="low")
    critical = queue.enqueue("critical", "critical", priority="critical")
    normal = queue.enqueue("normal", "normal", priority="normal")
    high = queue.enqueue("high", "high", priority="high")

    ordered = queue.ready_tasks()
    assert [task["title"] for task in ordered] == ["critical", "high", "normal", "low"]
    assert [task["priority"] for task in ordered] == [0, 1, 2, 3]


def test_ready_tasks_excludes_unmet_dependencies(repos):
    queue = make_queue(repos)
    done_dep = queue.enqueue("done dep", "done", task_id="done-dep")
    open_dep = queue.enqueue("open dep", "open", task_id="open-dep")
    ready = queue.enqueue("ready", "go", task_id="ready", depends_on=[done_dep])
    blocked = queue.enqueue("blocked", "wait", task_id="blocked", depends_on=[open_dep])
    missing = queue.enqueue("missing", "wait", task_id="missing", depends_on=["missing-dep"])
    repos.tasks.complete(done_dep)

    ready_ids = {task["id"] for task in queue.ready_tasks()}
    assert ready in ready_ids
    assert blocked not in ready_ids
    assert missing not in ready_ids


def test_illegal_transition_raises_task_state_error(repos):
    queue = make_queue(repos)
    task_id = queue.enqueue("queued", "not assigned yet")

    with pytest.raises(TaskStateError, match="dispatched"):
        queue.mark_in_progress(task_id)


@pytest.mark.asyncio
async def test_claim_next_is_single_winner_under_async_concurrency(repos, make_agent):
    make_agent("A1")
    make_agent("A2")
    make_agent("A3")
    queue = make_queue(repos)
    task_id = queue.enqueue("only once", "claim me", priority="critical")

    results = await pytest.importorskip("asyncio").gather(
        queue.claim_next("A1"),
        queue.claim_next("A2"),
        queue.claim_next("A3"),
    )

    winners = [task for task in results if task is not None]
    assert len(winners) == 1
    assert winners[0]["id"] == task_id
    assert repos.tasks.get(task_id)["state"] == "assigned"


def test_reassign_honors_max_retries_then_escalates(repos):
    queue = make_queue(repos)
    task_id = queue.enqueue("flaky", "try", max_retries=1)
    repos.tasks.fail(task_id, "first", state="failed")

    first = queue.reassign(task_id)
    assert first.reassigned is True
    assert first.escalated is False
    assert first.retry_count == 1
    task = repos.tasks.get(task_id)
    assert task["state"] == "queued"
    assert task["retry_count"] == 1

    repos.tasks.fail(task_id, "again", state="failed")
    second = queue.reassign(task_id)
    assert second.reassigned is False
    assert second.escalated is True
    assert second.retry_count == 1
    assert second.max_retries == 1
    assert repos.tasks.get(task_id)["state"] == "failed"


def test_templates_register_and_from_template(repos):
    queue = make_queue(repos)
    queue.register_template(
        "review",
        title="Review {module}",
        prompt="Review {module} for {focus}",
        description="QA pass for {module}",
        priority="high",
        max_retries=2,
    )

    task_id = queue.from_template("review", {"module": "dispatch", "focus": "races"})
    task = repos.tasks.get(task_id)
    assert task["title"] == "Review dispatch"
    assert task["prompt"] == "Review dispatch for races"
    assert task["description"] == "QA pass for dispatch"
    assert task["priority"] == 1
    assert task["max_retries"] == 2

    with pytest.raises(KeyError):
        queue.from_template("review", {"module": "dispatch"})


@pytest.mark.asyncio
async def test_injector_waits_for_idle_before_pane_send(repos, make_agent, mock_herdr_adapter, tmp_path):
    queue = make_queue(repos)
    task = await assigned_task(queue, make_agent, prompt="hello")
    injector = DispatchInjector(mock_herdr_adapter, queue, repos.agents, injector_config(tmp_path))

    result = await injector.dispatch(task)

    assert result.status == "in_progress"
    call_names = [name for name, _args, _kwargs in mock_herdr_adapter.calls]
    assert call_names.index("agent_wait") < call_names.index("pane_send")
    assert repos.tasks.get(task["id"])["state"] == "in_progress"


@pytest.mark.asyncio
async def test_injector_chunks_long_prompts(repos, make_agent, mock_herdr_adapter, tmp_path):
    queue = make_queue(repos)
    task = await assigned_task(queue, make_agent, prompt="abcdefghijkl")
    injector = DispatchInjector(
        mock_herdr_adapter,
        queue,
        repos.agents,
        injector_config(tmp_path, max_chunk_chars=5, file_fallback_threshold_chars=100),
    )

    result = await injector.dispatch(task)

    assert result.prompt_file is None
    assert sent_texts(mock_herdr_adapter) == ["abcde", "fghij", "kl", "\r"]


@pytest.mark.asyncio
async def test_injector_uses_file_fallback_over_threshold(repos, make_agent, mock_herdr_adapter, tmp_path):
    queue = make_queue(repos)
    long_prompt = "x" * 25
    task = await assigned_task(queue, make_agent, prompt=long_prompt)
    injector = DispatchInjector(
        mock_herdr_adapter,
        queue,
        repos.agents,
        injector_config(tmp_path, file_fallback_threshold_chars=10),
    )

    result = await injector.dispatch(task)

    assert result.status == "in_progress"
    assert result.prompt_file is not None
    assert result.prompt_file.read_text(encoding="utf-8") == long_prompt
    texts = sent_texts(mock_herdr_adapter)
    assert texts[0].startswith("Read and execute this HerdMaster task prompt:")
    assert str(result.prompt_file) in texts[0]
    assert texts[-1] == "\r"


@pytest.mark.asyncio
async def test_injector_uses_file_fallback_on_send_failure(repos, make_agent, mock_herdr_adapter, tmp_path, monkeypatch):
    queue = make_queue(repos)
    prompt = "short prompt"
    task = await assigned_task(queue, make_agent, prompt=prompt)
    calls = []

    async def flaky_send(pane_id, text, *, confirm=True, timeout=None):
        calls.append((pane_id, text, confirm, timeout))
        if len(calls) == 1:
            raise HerdrError("send failed")
        mock_herdr_adapter.calls.append(("pane_send", (pane_id, text), {"confirm": confirm, "timeout": timeout}))

    monkeypatch.setattr(mock_herdr_adapter, "pane_send", flaky_send)
    injector = DispatchInjector(
        mock_herdr_adapter,
        queue,
        repos.agents,
        injector_config(tmp_path, max_chunk_chars=100, file_fallback_threshold_chars=100),
    )

    result = await injector.dispatch(task)

    assert result.status == "in_progress"
    assert result.prompt_file is not None
    assert result.prompt_file.read_text(encoding="utf-8") == prompt
    assert [text for _pane, text, _confirm, _timeout in calls] == [prompt, "\x15", sent_texts(mock_herdr_adapter)[1], "\r"]


@pytest.mark.asyncio
async def test_injector_requeues_when_agent_never_idle(repos, make_agent, mock_herdr_adapter, tmp_path):
    queue = make_queue(repos)
    task = await assigned_task(queue, make_agent, prompt="wait", max_retries=3)
    mock_herdr_adapter.wait_results = [HerdrError("busy")]
    injector = DispatchInjector(
        mock_herdr_adapter,
        queue,
        repos.agents,
        injector_config(tmp_path, retry_attempts=1),
    )

    result = await injector.dispatch(task)

    assert result.status == "requeued"
    stored = repos.tasks.get(task["id"])
    assert stored["state"] == "queued"
    assert stored["assigned_to"] is None
    assert stored["retry_count"] == 1
    assert sent_texts(mock_herdr_adapter) == []


@pytest.mark.asyncio
async def test_injector_idempotency_guard_skips_stale_task(repos, make_agent, mock_herdr_adapter, tmp_path):
    queue = make_queue(repos)
    stale = await assigned_task(queue, make_agent, prompt="old")
    queue.mark_dispatched(stale["id"])
    queue.mark_in_progress(stale["id"])
    injector = DispatchInjector(mock_herdr_adapter, queue, repos.agents, injector_config(tmp_path))

    result = await injector.dispatch({**stale, "state": "assigned"})

    assert result.status == "skipped"
    assert result.attempts == 0
    assert mock_herdr_adapter.calls == []


@pytest.mark.asyncio
async def test_injector_uses_adapter_only_no_direct_subprocess(repos, make_agent, mock_herdr_adapter, tmp_path, monkeypatch):
    queue = make_queue(repos)
    task = await assigned_task(queue, make_agent, prompt="adapter")

    async def forbidden_subprocess(*_args, **_kwargs):
        raise AssertionError("DispatchInjector must not create subprocesses directly")

    monkeypatch.setattr("asyncio.create_subprocess_exec", forbidden_subprocess)
    injector = DispatchInjector(mock_herdr_adapter, queue, repos.agents, injector_config(tmp_path))

    result = await injector.dispatch(task)

    assert result.status == "in_progress"
    assert [name for name, _args, _kwargs in mock_herdr_adapter.calls] == [
        "agent_wait",
        "pane_send",
        "pane_send",
    ]

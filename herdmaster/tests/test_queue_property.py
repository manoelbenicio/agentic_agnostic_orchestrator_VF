from __future__ import annotations

from itertools import combinations, permutations

import pytest

from herdmaster.dispatch.queue import PRIORITIES, TaskQueue, TaskStateError


PRIORITY_NAMES = tuple(PRIORITIES.keys())
PRIORITY_COMBINATIONS = [
    combo
    for size in range(1, len(PRIORITY_NAMES) + 1)
    for combo in combinations(PRIORITY_NAMES, size)
]
PRIORITY_PERMUTATIONS = list(permutations(PRIORITY_NAMES))


def make_queue(repos):
    return TaskQueue(repos.tasks, repos.agents)


@pytest.mark.parametrize("priorities", PRIORITY_COMBINATIONS)
def test_ready_tasks_order_by_priority_for_any_combination(repos, priorities):
    queue = make_queue(repos)
    for name in reversed(priorities):
        queue.enqueue(f"{name} task", name, priority=name)

    ordered = queue.ready_tasks()

    assert [task["priority"] for task in ordered] == sorted(PRIORITIES[name] for name in priorities)
    assert [task["title"] for task in ordered] == [
        f"{name} task" for name in sorted(priorities, key=PRIORITIES.__getitem__)
    ]


@pytest.mark.parametrize("priorities", PRIORITY_PERMUTATIONS)
def test_ready_tasks_order_by_priority_for_any_insertion_order(repos, priorities):
    queue = make_queue(repos)
    ids_by_priority = {}
    for name in priorities:
        ids_by_priority[name] = queue.enqueue(f"{name} task", name, priority=name)

    assert [task["id"] for task in queue.ready_tasks()] == [
        ids_by_priority[name] for name in sorted(PRIORITY_NAMES, key=PRIORITIES.__getitem__)
    ]


def test_ready_tasks_preserve_fifo_for_same_priority(repos):
    queue = make_queue(repos)
    task_ids = [
        queue.enqueue("first", "prompt", priority="normal"),
        queue.enqueue("second", "prompt", priority="normal"),
        queue.enqueue("third", "prompt", priority="normal"),
    ]
    for index, task_id in enumerate(task_ids, start=1):
        repos.tasks.conn.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            (f"2026-01-01 00:00:0{index}", task_id),
        )
    repos.tasks.conn.commit()

    assert [task["id"] for task in queue.ready_tasks()] == task_ids


def test_retry_count_only_increases_and_then_stays_at_max(repos):
    queue = make_queue(repos)
    task_id = queue.enqueue("flaky", "retry me", max_retries=3)
    observed_retry_counts = [repos.tasks.get(task_id)["retry_count"]]

    for attempt in range(3):
        repos.tasks.fail(task_id, f"failure {attempt}", state="failed")
        result = queue.reassign(task_id)
        assert result.reassigned is True
        observed_retry_counts.append(repos.tasks.get(task_id)["retry_count"])

    repos.tasks.fail(task_id, "exhausted", state="failed")
    result = queue.reassign(task_id)

    assert result.reassigned is False
    assert result.escalated is True
    observed_retry_counts.append(repos.tasks.get(task_id)["retry_count"])
    assert observed_retry_counts == sorted(observed_retry_counts)
    assert observed_retry_counts == [0, 1, 2, 3, 3]


@pytest.mark.parametrize("terminal_state", ["done", "failed", "cancelled"])
def test_terminal_states_are_not_ready_or_implicitly_reenqueued(repos, terminal_state):
    queue = make_queue(repos)
    task_id = queue.enqueue(f"{terminal_state} task", "terminal", priority="critical")
    if terminal_state == "done":
        repos.tasks.complete(task_id)
    elif terminal_state == "failed":
        repos.tasks.fail(task_id, "failed", state="failed")
    else:
        queue.cancel(task_id)

    task = repos.tasks.get(task_id)

    assert task["state"] == terminal_state
    assert task_id not in {ready["id"] for ready in queue.ready_tasks()}
    if terminal_state == "cancelled":
        with pytest.raises(TaskStateError, match="cannot reassign"):
            queue.reassign(task_id)


@pytest.mark.parametrize("priority", PRIORITY_NAMES)
def test_reenqueue_preserves_original_priority(repos, priority):
    queue = make_queue(repos)
    task_id = queue.enqueue("preserve priority", "retry", priority=priority, max_retries=1)
    original_priority = repos.tasks.get(task_id)["priority"]

    repos.tasks.fail(task_id, "retryable", state="failed")
    result = queue.reassign(task_id)

    task = repos.tasks.get(task_id)
    assert result.reassigned is True
    assert task["state"] == "queued"
    assert task["priority"] == original_priority == PRIORITIES[priority]


@pytest.mark.parametrize(
    "priorities",
    [
        [3, 0, 2, 1],
        [0, 1, 2, 3],
        [1, 3, 0, 2],
    ],
)
def test_integer_priority_values_order_numerically(repos, priorities):
    queue = make_queue(repos)
    ids_by_priority = {}
    for priority in priorities:
        ids_by_priority[priority] = queue.enqueue(
            f"priority {priority}", "prompt", priority=priority
        )

    assert [task["id"] for task in queue.ready_tasks()] == [
        ids_by_priority[priority] for priority in sorted(priorities)
    ]


@pytest.mark.parametrize("bad_priority", [-1, -100])
def test_negative_priority_is_rejected(repos, bad_priority):
    queue = make_queue(repos)
    with pytest.raises(ValueError, match="non-negative"):
        queue.enqueue("bad priority", "prompt", priority=bad_priority)


@pytest.mark.parametrize("bad_priority", ["urgent", "Medium", "super_high", "", "  "])
def test_unknown_priority_name_is_rejected(repos, bad_priority):
    queue = make_queue(repos)
    with pytest.raises(ValueError, match="unknown priority"):
        queue.enqueue("bad priority", "prompt", priority=bad_priority)


@pytest.mark.parametrize("state", ["queued", "assigned", "dispatched", "in_progress"])
@pytest.mark.asyncio
async def test_reassign_rejects_non_retriable_states(repos, state):
    repos.agents.upsert("A1", "Agent 1", "codex", "worker")
    queue = make_queue(repos)
    task_id = queue.enqueue("non retriable", "prompt", max_retries=2)

    if state == "assigned":
        await queue.claim_next("A1")
    elif state == "dispatched":
        await queue.claim_next("A1")
        queue.mark_dispatched(task_id)
    elif state == "in_progress":
        await queue.claim_next("A1")
        queue.mark_dispatched(task_id)
        queue.mark_in_progress(task_id)

    with pytest.raises(TaskStateError, match="cannot reassign"):
        queue.reassign(task_id)


@pytest.mark.asyncio
async def test_reassign_escalates_after_max_retries_without_requeue(repos):
    repos.agents.upsert("A1", "Agent 1", "codex", "worker")
    queue = make_queue(repos)
    task_id = queue.enqueue("escalate", "prompt", max_retries=1)

    await queue.claim_next("A1")
    queue.mark_dispatched(task_id)
    queue.mark_in_progress(task_id)
    queue.mark_failed(task_id, "first")
    first = queue.reassign(task_id)

    await queue.claim_next("A1")
    queue.mark_dispatched(task_id)
    queue.mark_in_progress(task_id)
    queue.mark_failed(task_id, "second")
    second = queue.reassign(task_id)

    assert first.reassigned is True
    assert first.escalated is False
    assert second.reassigned is False
    assert second.escalated is True
    assert repos.tasks.get(task_id)["state"] == "failed"

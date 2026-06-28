from __future__ import annotations

import asyncio

import pytest

from orchestrator import ApprovalRequired, TechLeadConfig, TechLeadCoordinator
from scheduler import QuotaAwareScheduler, QuotaLedger, QuotaSnapshot
from seats.pool import Seat, SeatPool


class FakePlanner:
    async def decompose(self, objective, workers):
        return [
            {
                "task_id": f"task-{worker}",
                "worker_id": worker,
                "prompt": f"{objective}: {worker}",
                "estimated_burn_seconds": 60,
            }
            for worker in workers
        ]


def test_techlead_fanout_inherits_parent_seat_without_extra_pool_acquire() -> None:
    async def scenario() -> None:
        pool = SeatPool()
        parent = Seat("lead-seat", "tenant-1", "codex", "/tmp/lead", token="configured-token")
        pool.register_seat(parent)
        parent_seat = await pool.acquire("tenant-1", "codex")
        dispatched = []

        async def dispatch(task):
            dispatched.append(task)

        scheduler = QuotaAwareScheduler(QuotaLedger(), max_concurrent=20)
        coordinator = TechLeadCoordinator(
            TechLeadConfig(
                tenant_id="tenant-1",
                project_id="project-1",
                tech_lead_agent_id="lead",
                tech_lead_seat_id=parent_seat.seat_id,
                vendor="codex",
                autonomy_level=4,
                max_fanout=3,
            ),
            seat_pool=pool,
            scheduler=scheduler,
            dispatch=dispatch,
            planner=FakePlanner(),
        )

        result = await coordinator.execute(
            "build feature",
            permitted_workers=("w1", "w2", "w3", "w4"),
            parent_seat=parent_seat,
        )

        assert [task.worker_id for task in result.tasks] == ["w1", "w2", "w3"]
        assert len(dispatched) == 3
        assert {task.credential_ref for task in dispatched} == {"seat://lead-seat"}
        assert parent_seat.ref_count == 4

    asyncio.run(scenario())


def test_low_autonomy_requires_human_approval_before_spawn() -> None:
    async def scenario() -> None:
        pool = SeatPool()
        parent = Seat("lead-seat", "tenant-1", "codex", "/tmp/lead", token="configured-token")
        pool.register_seat(parent)
        parent_seat = await pool.acquire("tenant-1", "codex")
        dispatched = []

        async def dispatch(task):
            dispatched.append(task)

        coordinator = TechLeadCoordinator(
            TechLeadConfig(
                tenant_id="tenant-1",
                project_id="project-1",
                tech_lead_agent_id="lead",
                tech_lead_seat_id="lead-seat",
                vendor="codex",
                autonomy_level=1,
            ),
            seat_pool=pool,
            scheduler=QuotaAwareScheduler(QuotaLedger()),
            dispatch=dispatch,
            planner=FakePlanner(),
        )

        with pytest.raises(ApprovalRequired):
            await coordinator.execute("build feature", permitted_workers=("w1",), parent_seat=parent_seat)

        assert dispatched == []
        assert parent_seat.ref_count == 1

    asyncio.run(scenario())


def test_scheduler_quota_throttles_excess_fanout_to_queue() -> None:
    async def scenario() -> None:
        pool = SeatPool()
        parent = Seat("lead-seat", "tenant-1", "codex", "/tmp/lead", token="configured-token")
        pool.register_seat(parent)
        parent_seat = await pool.acquire("tenant-1", "codex")
        dispatched = []

        async def dispatch(task):
            dispatched.append(task)

        quota = QuotaLedger(
            {
                "codex": QuotaSnapshot(
                    vendor="codex",
                    five_hour_cap_seconds=120,
                    weekly_cap_seconds=120,
                    used_five_hour_seconds=0,
                    used_weekly_seconds=0,
                )
            }
        )
        coordinator = TechLeadCoordinator(
            TechLeadConfig(
                tenant_id="tenant-1",
                project_id="project-1",
                tech_lead_agent_id="lead",
                tech_lead_seat_id="lead-seat",
                vendor="codex",
                autonomy_level=4,
                max_fanout=3,
            ),
            seat_pool=pool,
            scheduler=QuotaAwareScheduler(quota),
            dispatch=dispatch,
            planner=FakePlanner(),
        )

        result = await coordinator.execute("build feature", permitted_workers=("w1", "w2", "w3"), parent_seat=parent_seat)

        assert len(result.dispatched) == 2
        assert len(result.queued) == 1
        assert len(dispatched) == 2

    asyncio.run(scenario())

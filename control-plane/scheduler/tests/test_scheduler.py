from __future__ import annotations

import asyncio
from datetime import timedelta
from random import Random

from core import TaskEnvelope
from scheduler import (
    AdmissionStatus,
    BackoffPolicy,
    QuotaAwareScheduler,
    QuotaLedger,
    QuotaSnapshot,
    VendorRateLimitError,
)


class FakeRedisHash:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))


def task(task_id: str = "task-1", seat_seconds: int = 60) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        tenant_id="tenant-1",
        project_id="project-1",
        assignee_runtime="codex",
        prompt="work",
        budget={"seat_seconds": seat_seconds},
        credential_ref="seat://s1",
        operation_mode="socket",
    )


def test_admission_reserves_quota_for_dispatch() -> None:
    quota = QuotaLedger({"codex": QuotaSnapshot(vendor="codex", weekly_cap_seconds=300, five_hour_cap_seconds=300)})
    scheduler = QuotaAwareScheduler(quota)

    decision = scheduler.admit(task(seat_seconds=120))

    assert decision.status is AdmissionStatus.DISPATCH
    assert quota.snapshot("codex").used_weekly_seconds == 120


def test_quota_exhaustion_queues_without_failure() -> None:
    quota = QuotaLedger(
        {
            "codex": QuotaSnapshot(
                vendor="codex",
                weekly_cap_seconds=100,
                five_hour_cap_seconds=100,
                used_weekly_seconds=90,
                used_five_hour_seconds=90,
            )
        }
    )
    scheduler = QuotaAwareScheduler(quota)

    decision = scheduler.admit(task(seat_seconds=30))

    assert decision.status is AdmissionStatus.WAITING_ON_QUOTA
    assert len(scheduler.queue) == 1


def test_concurrency_ceiling_queues_ready_tasks() -> None:
    scheduler = QuotaAwareScheduler(QuotaLedger(), max_concurrent=1)
    scheduler.running_count = 1

    decision = scheduler.admit(task())

    assert decision.status is AdmissionStatus.WAITING_ON_CONCURRENCY
    assert scheduler.queue[0].reason == "concurrency ceiling reached"


def test_backoff_retries_429_and_then_queues() -> None:
    async def scenario() -> None:
        delays = []

        async def sleep(delay):
            delays.append(delay)

        async def dispatch(_task):
            raise VendorRateLimitError(429)

        scheduler = QuotaAwareScheduler(
            QuotaLedger(),
            backoff=BackoffPolicy(base_seconds=1, jitter_ratio=0),
            sleep=sleep,
        )

        result = await scheduler.dispatch_with_backoff(task(), dispatch, attempts=3)

        assert result is None
        assert delays == [1, 2]
        assert scheduler.backoff_log == [1, 2]
        assert scheduler.queue[-1].reason == "rate limited after 3 attempts"

    asyncio.run(scenario())


def test_backoff_jitter_is_bounded() -> None:
    policy = BackoffPolicy(base_seconds=2, max_seconds=10, jitter_ratio=0.5)

    delay = policy.delay(2, rng=Random(1))

    assert 4 <= delay <= 6


def test_burn_rate_forecast_flags_24h_exhaustion() -> None:
    quota = QuotaLedger(
        {
            "codex": QuotaSnapshot(
                vendor="codex",
                weekly_cap_seconds=3600,
                five_hour_cap_seconds=3600,
                used_weekly_seconds=1800,
                used_five_hour_seconds=1800,
            )
        }
    )

    forecast = quota.forecast("codex", observed_burn_seconds=1800, observed_window=timedelta(hours=1))

    assert forecast.burn_rate_seconds_per_hour == 1800
    assert forecast.hours_until_exhaustion == 1
    assert forecast.will_exhaust_within_24h is True


def test_quota_ledger_persists_snapshots_across_restart() -> None:
    redis = FakeRedisHash()
    first = QuotaLedger(redis_client=redis)

    first.reserve("codex", 120)

    restarted = QuotaLedger(redis_client=redis)

    assert restarted.snapshot("codex").used_weekly_seconds == 120
    assert restarted.snapshot("codex").used_five_hour_seconds == 120

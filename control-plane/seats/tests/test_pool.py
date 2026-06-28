import asyncio
import time

import pytest

from ..pool import Seat, SeatPool


@pytest.fixture
def seat_pool():
    return SeatPool()


def _provider(seat: Seat) -> str:
    return f"test-token-{seat.seat_id}-{time.time()}"


def test_acquire_and_release(seat_pool):
    async def scenario():
        seat = Seat("s1", "tenant_a", "vendor_x", "/tmp/home_s1", token_provider=_provider)
        seat_pool.register_seat(seat)

        acquired_seat = await asyncio.wait_for(seat_pool.acquire("tenant_a", "vendor_x"), timeout=1.0)
        assert acquired_seat.seat_id == "s1"
        assert acquired_seat.ref_count == 1
        assert "test-token-" in acquired_seat.token

        seat_pool.release(acquired_seat)
        assert acquired_seat.ref_count == 0

        acquired_seat_2 = await asyncio.wait_for(seat_pool.acquire("tenant_a", "vendor_x"), timeout=1.0)
        assert acquired_seat_2.seat_id == "s1"

    asyncio.run(scenario())


def test_acquire_without_token_provider_fails_high(seat_pool):
    async def scenario():
        seat = Seat("s1", "tenant_a", "vendor_x", "/tmp/home_s1")
        seat_pool.register_seat(seat)

        with pytest.raises(RuntimeError, match="no token provider is configured"):
            await seat_pool.acquire("tenant_a", "vendor_x")

    asyncio.run(scenario())


def test_queueing_when_no_seats_available(seat_pool):
    async def scenario():
        seat = Seat("s1", "tenant_a", "vendor_x", "/tmp/home_s1", token="configured-token")
        seat_pool.register_seat(seat)

        seat1 = await seat_pool.acquire("tenant_a", "vendor_x")
        acquire_task = asyncio.create_task(seat_pool.acquire("tenant_a", "vendor_x"))

        done, pending = await asyncio.wait([acquire_task], timeout=0.1)
        assert not done

        seat_pool.release(seat1)

        seat2 = await asyncio.wait_for(acquire_task, timeout=1.0)
        assert seat2.seat_id == "s1"

    asyncio.run(scenario())


def test_subagent_inherits_seat(seat_pool):
    async def scenario():
        seat = Seat("s1", "tenant_a", "vendor_x", "/tmp/home_s1", token="configured-token")
        seat_pool.register_seat(seat)

        parent_seat = await seat_pool.acquire("tenant_a", "vendor_x")
        assert parent_seat.ref_count == 1

        subagent_seat = seat_pool.acquire_subagent(parent_seat)
        assert subagent_seat.seat_id == "s1"
        assert subagent_seat.ref_count == 2

        seat_pool.release(parent_seat)
        assert subagent_seat.ref_count == 1

        seat_pool.release(subagent_seat)
        assert subagent_seat.ref_count == 0

        new_seat = await asyncio.wait_for(seat_pool.acquire("tenant_a", "vendor_x"), timeout=1.0)
        assert new_seat.seat_id == "s1"

    asyncio.run(scenario())


def test_credential_isolation_env():
    seat1 = Seat("s1", "tenant_a", "vendor_x", "/tmp/home_s1")
    seat2 = Seat("s2", "tenant_a", "vendor_x", "/tmp/home_s2")

    env1 = seat1.get_env()
    env2 = seat2.get_env()

    assert env1["HOME"] == "/tmp/home_s1"
    assert env2["HOME"] == "/tmp/home_s2"
    assert env1["SEAT_ID"] == "s1"
    assert env2["SEAT_ID"] == "s2"
    assert env1["HOME"] != env2["HOME"]


def test_lease_affinity_and_refresh(seat_pool):
    async def scenario():
        seat = Seat("s1", "tenant_a", "vendor_x", "/tmp/home_s1", token_lifetime=0.1, token_provider=_provider)
        seat_pool.register_seat(seat)

        acquired_seat = await seat_pool.acquire("tenant_a", "vendor_x")
        first_token = acquired_seat.token

        await asyncio.sleep(0.15)

        seat_pool.release(acquired_seat)
        re_acquired_seat = await seat_pool.acquire("tenant_a", "vendor_x")

        assert re_acquired_seat.seat_id == "s1"
        assert re_acquired_seat.token != first_token

    asyncio.run(scenario())

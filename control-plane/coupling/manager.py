"""ADR-001 coupling manager with retry, backoff, runtime checks, and idempotency."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from .models import CouplingPhase, CouplingStatus

Probe = Callable[[], bool | Awaitable[bool]]
Sleep = Callable[[float], Awaitable[None]]


class CouplingManager:
    """Manage soft coupling lifecycle for Herdr and HerdMaster.

    Initial connection failures degrade instead of raising, preserving NFR-009.
    Runtime failures after a connected state transition to disconnected.
    """

    def __init__(
        self,
        *,
        herdr_probe: Probe,
        herdmaster_probe: Probe,
        backoff_delays: Sequence[float] = (0.1, 0.2, 0.4),
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.herdr_probe = herdr_probe
        self.herdmaster_probe = herdmaster_probe
        self.backoff_delays = tuple(backoff_delays)
        self.sleep = sleep
        self._status = CouplingStatus(CouplingPhase.DISCONNECTED)
        self._lock = asyncio.Lock()

    @property
    def status(self) -> CouplingStatus:
        """Return the last observed coupling status."""
        return self._status

    async def connect(self) -> CouplingStatus:
        """Try to establish the coupling; no-op when already connected."""
        async with self._lock:
            if self._status.phase == CouplingPhase.CONNECTED:
                return self._status
            return await self._attempt_connect(degraded_on_failure=True)

    async def reconnect(self) -> CouplingStatus:
        """Retry manually; idempotent if already connected."""
        async with self._lock:
            if self._status.phase == CouplingPhase.CONNECTED:
                return self._status
            return await self._attempt_connect(degraded_on_failure=True)

    async def check_runtime(self) -> CouplingStatus:
        """Detect runtime drops after boot."""
        async with self._lock:
            try:
                await self._probe_all()
            except Exception as exc:
                self._status = CouplingStatus(
                    CouplingPhase.DISCONNECTED,
                    last_error=str(exc),
                    attempts=self._status.attempts,
                )
            else:
                self._status = CouplingStatus(
                    CouplingPhase.CONNECTED,
                    attempts=self._status.attempts,
                )
            return self._status

    async def _attempt_connect(self, *, degraded_on_failure: bool) -> CouplingStatus:
        attempts = 0
        last_error: str | None = None
        delays = (0.0, *self.backoff_delays)
        for delay in delays:
            if delay:
                await self.sleep(delay)
            attempts += 1
            try:
                await self._probe_all()
            except Exception as exc:
                last_error = str(exc)
                continue
            self._status = CouplingStatus(CouplingPhase.CONNECTED, attempts=attempts)
            return self._status

        self._status = CouplingStatus(
            CouplingPhase.DEGRADED if degraded_on_failure else CouplingPhase.DISCONNECTED,
            last_error=last_error,
            attempts=attempts,
        )
        return self._status

    async def _probe_all(self) -> None:
        herdr_ok = await self._probe(self.herdr_probe)
        if not herdr_ok:
            raise RuntimeError("Herdr probe returned false")
        herdmaster_ok = await self._probe(self.herdmaster_probe)
        if not herdmaster_ok:
            raise RuntimeError("HerdMaster probe returned false")

    @staticmethod
    async def _probe(probe: Probe) -> bool:
        result = probe()
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

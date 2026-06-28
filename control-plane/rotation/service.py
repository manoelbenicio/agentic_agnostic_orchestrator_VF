"""Account rotation orchestrator (state machine of doc 36 §3).

Composes AccountPool + AccountAuthenticator (+ optional QuotaLedger / tracer /
resume hook). The orchestration logic (lock, anti-thrash, priority selection,
park, status transitions) is implemented here; the runtime-specific steps
(logout/login/resume) are delegated to injected dependencies so this stays
testable with fakes and does NOT alter the current dispatch flow.

Not wired into app.main / dependencies yet — assembly happens in a rotation onda.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from .auth import AccountAuthenticator
from .models import Account, RotationOutcome, RotationReason, TaskSnapshot
from .pool import AccountPool

logger = logging.getLogger(__name__)

# Hook the runtime calls to "resume" a task on a freshly-authenticated account.
# (account, snapshot) -> None. Decouples rotation from executors (doc 36 §4).
ResumeHook = Callable[[Account, TaskSnapshot], None]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountRotationService:
    """Rotate an agent off an exhausted account onto the next available one."""

    def __init__(
        self,
        pool: AccountPool,
        authenticator: AccountAuthenticator,
        *,
        resume_hook: ResumeHook | None = None,
        login_timeout_s: float = 120.0,
        max_rotations_per_window: int = 8,
        max_login_attempts: int = 3,
    ) -> None:
        self.pool = pool
        self.authenticator = authenticator
        self.resume_hook = resume_hook
        self.login_timeout_s = login_timeout_s
        self.max_rotations_per_window = max_rotations_per_window
        self.max_login_attempts = max_login_attempts
        # Simple in-memory guards (move to redis/QuotaLedger in the onda).
        self._locks: set[str] = set()                 # agent_ids mid-rotation
        self._rotation_counts: dict[str, int] = {}     # task_id -> rotations this window

    def on_exhaustion(
        self,
        *,
        agent_id: str,
        tenant_id: str,
        current_account_id: str,
        snapshot: TaskSnapshot,
        reason: RotationReason = RotationReason.QUOTA_EXHAUSTED_REACTIVE,
        cooldown_until: datetime | None = None,
        vendor: str | None = None,
        now: datetime | None = None,
    ) -> RotationOutcome:
        """Execute the rotation state machine (doc 36 §3).

        Returns a RotationOutcome describing whether the agent rotated, parked
        (all accounts exhausted), or failed. Never raises on expected paths.
        """
        now = now or _utcnow()

        # 1) anti-thrash + per-agent lock
        if self._rotation_counts.get(snapshot.task_id, 0) >= self.max_rotations_per_window:
            return RotationOutcome(rotated=False, reason=reason, from_account=current_account_id,
                                   error="max rotations per window exceeded; parking to avoid thrash",
                                   parked=True, wake_at=self.pool.next_wake_at(tenant_id))
        if agent_id in self._locks:
            return RotationOutcome(rotated=False, reason=reason, from_account=current_account_id,
                                   error="rotation already in progress for agent")
        self._locks.add(agent_id)
        try:
            # 2) mark current account exhausted (+ cooldown)
            self.pool.mark_exhausted(current_account_id, cooldown_until=cooldown_until, now=now)

            # 3) logout current account (snapshot already captured by caller)
            current = self.pool.get(current_account_id)
            if current is not None:
                try:
                    self.authenticator.logout(current)
                except Exception:  # logout failure must not block rotation
                    logger.warning("logout failed for account %s", current_account_id, exc_info=True)

            # 4) select next account by expertise priority, retrying on login failure
            tried: set[str] = {current_account_id}
            for _ in range(self.max_login_attempts):
                nxt = self.pool.select_next(vendor, tenant_id, now=now, exclude=tried)
                if nxt is None:
                    break  # nothing available → park
                tried.add(nxt.account_id)
                if self._try_login_and_resume(nxt, snapshot):
                    self.pool.lease(nxt.account_id, agent_id)
                    self._rotation_counts[snapshot.task_id] = self._rotation_counts.get(snapshot.task_id, 0) + 1
                    return RotationOutcome(rotated=True, reason=reason,
                                           from_account=current_account_id, to_account=nxt.account_id)
                self.pool.mark_degraded(nxt.account_id, "login/resume failed during rotation")

            # 5) nothing usable → park with ETA of earliest reset
            return RotationOutcome(rotated=False, reason=reason, from_account=current_account_id,
                                   parked=True, wake_at=self.pool.next_wake_at(tenant_id),
                                   error="no available account; parked until quota reset")
        finally:
            self._locks.discard(agent_id)

    def _try_login_and_resume(self, account: Account, snapshot: TaskSnapshot) -> bool:
        """Login the next account and resume the task; True on success."""
        try:
            session_id = self.authenticator.login(account)
            if not self.authenticator.wait_authenticated(session_id, timeout_s=self.login_timeout_s):
                return False
            if self.resume_hook is not None:
                self.resume_hook(account, snapshot)
            return True
        except NotImplementedError:
            raise  # surface unimplemented runtime wiring loudly during the onda
        except Exception:
            logger.warning("login/resume failed for account %s", account.account_id, exc_info=True)
            return False

    def reset_window_counters(self) -> None:
        """Clear per-window rotation counters (call when windows reset)."""
        self._rotation_counts.clear()

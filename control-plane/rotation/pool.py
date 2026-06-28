"""Account pool with quota windows and expertise-priority selection.

Sits on top of the existing ``seats.SeatPool`` concept (each Account is backed by
a Seat for credential isolation). This pool adds the quota-window state machine
and the priority-based selection required by the rotation scenario (doc 36).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Account, AccountStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountPool:
    """In-memory registry of rotation accounts.

    Selection is by **expertise priority** (Codex > Opus > Antigravity > fallback),
    then by most remaining quota, then by account_id for determinism. An account
    is leased to a single agent at a time (anti-collision, doc 36 §5).
    """

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        # account_id -> agent_id currently holding the lease
        self._leases: dict[str, str] = {}

    # ---- registration -------------------------------------------------------
    def register(self, account: Account) -> None:
        """Add or replace an account in the pool."""
        self._accounts[account.account_id] = account

    def get(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    def all(self) -> list[Account]:
        return list(self._accounts.values())

    # ---- selection ----------------------------------------------------------
    def select_next(
        self,
        vendor: str | None,
        tenant_id: str,
        *,
        now: datetime | None = None,
        exclude: set[str] | None = None,
    ) -> Account | None:
        """Return the next selectable account by expertise priority.

        ``vendor=None`` lets the selector cross vendors strictly by priority
        (Codex first, then Opus, then Antigravity), which is the desired behavior
        when an agent's task isn't pinned to a single vendor. When ``vendor`` is
        set, only that vendor's accounts are considered.
        """
        now = now or _utcnow()
        exclude = exclude or set()
        candidates = [
            acc
            for acc in self._accounts.values()
            if acc.account_id not in exclude
            and acc.tenant_id == tenant_id
            and (vendor is None or acc.vendor.lower() == vendor.lower())
            and acc.is_selectable(now=now)
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda a: (
                a.effective_priority,                       # expertise priority first
                -(a.tokens_per_window - a.tokens_used),     # most remaining quota
                a.account_id,                               # deterministic tiebreak
            )
        )
        return candidates[0]

    def next_wake_at(self, tenant_id: str) -> datetime | None:
        """Earliest cooldown_until among exhausted accounts (for parking ETA)."""
        times = [
            acc.cooldown_until
            for acc in self._accounts.values()
            if acc.tenant_id == tenant_id
            and acc.status in {AccountStatus.EXHAUSTED, AccountStatus.COOLDOWN}
            and acc.cooldown_until is not None
        ]
        return min(times) if times else None

    # ---- lease / status transitions ----------------------------------------
    def lease(self, account_id: str, agent_id: str) -> None:
        acc = self._require(account_id)
        self._leases[account_id] = agent_id
        acc.status = AccountStatus.LEASED

    def release(self, account_id: str) -> None:
        acc = self._require(account_id)
        self._leases.pop(account_id, None)
        if acc.status == AccountStatus.LEASED:
            acc.status = AccountStatus.AVAILABLE

    def mark_exhausted(
        self,
        account_id: str,
        *,
        cooldown_until: datetime | None = None,
        now: datetime | None = None,
    ) -> None:
        """Mark an account exhausted; cooldown defaults to window_seconds from now."""
        acc = self._require(account_id)
        now = now or _utcnow()
        acc.status = AccountStatus.EXHAUSTED
        acc.cooldown_until = cooldown_until or (now + timedelta(seconds=acc.window_seconds))
        self._leases.pop(account_id, None)

    def mark_degraded(self, account_id: str, reason: str) -> None:
        acc = self._require(account_id)
        acc.status = AccountStatus.DEGRADED
        acc.last_error = reason
        self._leases.pop(account_id, None)

    def refresh_windows(self, *, now: datetime | None = None) -> None:
        """Return cooled-down accounts to AVAILABLE and reset their window."""
        now = now or _utcnow()
        for acc in self._accounts.values():
            if (
                acc.status in {AccountStatus.EXHAUSTED, AccountStatus.COOLDOWN}
                and acc.cooldown_until is not None
                and now >= acc.cooldown_until
            ):
                acc.status = AccountStatus.AVAILABLE
                acc.cooldown_until = None
                acc.window_start = now
                acc.tokens_used = 0

    def _require(self, account_id: str) -> Account:
        acc = self._accounts.get(account_id)
        if acc is None:
            raise KeyError(f"unknown account: {account_id}")
        return acc

"""Domain models for automatic account rotation on token exhaustion.

Scenario & design: docs/30-COMPONENTES/36-ROTACAO-CONTAS-TOKEN.md
ADR-009.

An *account* is one vendor subscription. It maps onto a ``seats.Seat`` (isolated
``home_dir``/``config_dir``). When an account exhausts its rolling 5h (or weekly)
token window, the agent rotates to the next available account, by **model
expertise priority** (Codex > Opus > Antigravity > fallback).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

# Selection priority by model expertise (decision in doc 36 §5). Lower = higher
# priority. Vendors not listed fall back to DEFAULT_PRIORITY.
VENDOR_PRIORITY: dict[str, int] = {
    "codex": 1,
    "opus": 2,
    "claude": 2,  # Opus is served via Claude
    "glm": 2,
    "antigravity": 3,
}
DEFAULT_PRIORITY = 99
WINDOW_SECONDS_5H = 5 * 60 * 60  # 18000


class AccountStatus(StrEnum):
    """Lifecycle status of an account in the rotation pool."""

    AVAILABLE = "available"      # has quota, free to lease
    LEASED = "leased"            # currently in use by an agent
    EXHAUSTED = "exhausted"      # quota hit; waiting for cooldown_until
    COOLDOWN = "cooldown"        # explicit cooldown window (== exhausted, timed)
    DEGRADED = "degraded"        # login/credential problem; skip until fixed


class RotationReason(StrEnum):
    """Why a rotation was triggered."""

    QUOTA_EXHAUSTED_REACTIVE = "quota_exhausted_reactive"   # detected on-screen / 429
    QUOTA_FORECAST_PROACTIVE = "quota_forecast_proactive"   # ledger near cap
    LOGIN_FAILED = "login_failed"                           # next account auth failed
    MANUAL = "manual"                                       # operator/TL forced


@dataclass(slots=True)
class Account:
    """A vendor subscription that can be leased to an agent.

    Backed by a ``seats.Seat`` for credential isolation. Quota is a rolling
    window of ``window_seconds`` (default 5h) versus ``tokens_per_window``
    (varies per plan/company — doc 36 §6).
    """

    account_id: str
    vendor: str
    tenant_id: str
    seat_id: str
    home_dir: str
    config_dir: str
    auth_mode: str = "device"            # device-login / OAuth only (doc 36 §7)
    priority: int | None = None          # override; else derived from VENDOR_PRIORITY
    tokens_per_window: int = 0           # 0 = unknown/unbounded
    window_seconds: int = WINDOW_SECONDS_5H
    status: AccountStatus = AccountStatus.AVAILABLE
    window_start: datetime | None = None
    tokens_used: int = 0
    cooldown_until: datetime | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_priority(self) -> int:
        """Resolved selection priority (explicit override wins)."""
        if self.priority is not None:
            return self.priority
        return VENDOR_PRIORITY.get(self.vendor.lower(), DEFAULT_PRIORITY)

    def is_selectable(self, *, now: datetime) -> bool:
        """True when the account may be leased right now."""
        if self.status in {AccountStatus.LEASED, AccountStatus.DEGRADED}:
            return False
        if self.status in {AccountStatus.EXHAUSTED, AccountStatus.COOLDOWN}:
            return self.cooldown_until is not None and now >= self.cooldown_until
        return True


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    """Minimal state captured before logout so the task can be RESTARTED.

    Context is NOT portable across accounts (doc 36 §3) — resume means re-running
    from the original prompt and the last durable checkpoint, not continuing the
    live session.
    """

    task_id: str
    prompt: str
    cwd: str | None = None
    checkpoint_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RotationOutcome:
    """Result of a rotation attempt."""

    rotated: bool
    reason: RotationReason
    from_account: str | None = None
    to_account: str | None = None
    parked: bool = False
    wake_at: datetime | None = None
    error: str | None = None

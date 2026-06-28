"""Tests for the account-rotation skeleton (pure logic, no runtime deps)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rotation import (
    Account,
    AccountPool,
    AccountRotationService,
    AccountStatus,
    QuotaExhaustionDetector,
    RotationReason,
    TaskSnapshot,
)


def _now() -> datetime:
    return datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc)


def _acct(account_id: str, vendor: str, *, tenant="t1", tokens_per_window=1_000_000) -> Account:
    return Account(
        account_id=account_id,
        vendor=vendor,
        tenant_id=tenant,
        seat_id=f"seat-{account_id}",
        home_dir=f"/srv/aop/seats/{account_id}",
        config_dir=f"/srv/aop/seats/{account_id}/cfg",
        tokens_per_window=tokens_per_window,
    )


class FakeAuthenticator:
    """In-memory authenticator that always succeeds (for orchestration tests)."""

    def __init__(self) -> None:
        self.logged_out: list[str] = []
        self.logged_in: list[str] = []

    def logout(self, account):
        self.logged_out.append(account.account_id)

    def login(self, account) -> str:
        self.logged_in.append(account.account_id)
        return f"sess-{account.account_id}"

    def wait_authenticated(self, session_id, *, timeout_s):
        return True


# ---- detector ---------------------------------------------------------------
def test_detector_matches_each_vendor():
    d = QuotaExhaustionDetector()
    assert d.detect_text("codex", "You've hit your usage limit, try again at 3:51 PM").exhausted
    assert d.detect_text("opus", "Claude usage limit reached. Your limit will reset at 2pm").exhausted
    assert d.detect_text("antigravity", "You have reached the quota limit for this model.").exhausted
    assert not d.detect_text("codex", "all good, working...").exhausted


def test_detector_429_is_quota_503_is_overload():
    d = QuotaExhaustionDetector()
    assert d.detect_status_code("codex", 429).exhausted
    sig = d.detect_status_code("antigravity", 503)
    assert not sig.exhausted and sig.is_server_overload  # 503 must NOT trigger rotation


def test_detector_extracts_reset_hint():
    d = QuotaExhaustionDetector()
    sig = d.detect_text("opus", "5-hour limit reached · resets 6am (Asia/Seoul)")
    assert sig.exhausted and sig.reset_hint is not None


# ---- pool selection by expertise priority ----------------------------------
def test_select_next_prefers_codex_then_opus_then_antigravity():
    pool = AccountPool()
    pool.register(_acct("ag-1", "antigravity"))
    pool.register(_acct("op-1", "opus"))
    pool.register(_acct("cx-1", "codex"))
    chosen = pool.select_next(None, "t1", now=_now())
    assert chosen.account_id == "cx-1"  # Codex wins by priority


def test_select_next_skips_exhausted_until_cooldown():
    pool = AccountPool()
    pool.register(_acct("cx-1", "codex"))
    pool.register(_acct("op-1", "opus"))
    pool.mark_exhausted("cx-1", now=_now())  # codex on cooldown
    chosen = pool.select_next(None, "t1", now=_now())
    assert chosen.account_id == "op-1"  # falls back to next priority


def test_refresh_windows_returns_cooled_down_accounts():
    pool = AccountPool()
    pool.register(_acct("cx-1", "codex"))
    pool.mark_exhausted("cx-1", cooldown_until=_now() + timedelta(hours=5), now=_now())
    pool.refresh_windows(now=_now() + timedelta(hours=5, seconds=1))
    assert pool.get("cx-1").status is AccountStatus.AVAILABLE


# ---- rotation orchestration -------------------------------------------------
def test_rotation_switches_to_next_priority_account():
    pool = AccountPool()
    pool.register(_acct("cx-1", "codex"))
    pool.register(_acct("op-1", "opus"))
    pool.lease("cx-1", "agent-X")
    svc = AccountRotationService(pool, FakeAuthenticator())

    outcome = svc.on_exhaustion(
        agent_id="agent-X",
        tenant_id="t1",
        current_account_id="cx-1",
        snapshot=TaskSnapshot(task_id="task-1", prompt="do work"),
        now=_now(),
    )
    assert outcome.rotated is True
    assert outcome.from_account == "cx-1"
    assert outcome.to_account == "op-1"
    assert pool.get("cx-1").status is AccountStatus.EXHAUSTED
    assert pool.get("op-1").status is AccountStatus.LEASED


def test_rotation_parks_when_all_exhausted():
    pool = AccountPool()
    pool.register(_acct("cx-1", "codex"))
    pool.lease("cx-1", "agent-X")
    svc = AccountRotationService(pool, FakeAuthenticator())

    outcome = svc.on_exhaustion(
        agent_id="agent-X",
        tenant_id="t1",
        current_account_id="cx-1",
        snapshot=TaskSnapshot(task_id="task-1", prompt="do work"),
        cooldown_until=_now() + timedelta(hours=5),
        now=_now(),
    )
    assert outcome.rotated is False
    assert outcome.parked is True
    assert outcome.wake_at == _now() + timedelta(hours=5)


def test_rotation_anti_thrash_caps_rotations():
    pool = AccountPool()
    for i in range(10):
        pool.register(_acct(f"cx-{i}", "codex"))
    svc = AccountRotationService(pool, FakeAuthenticator(), max_rotations_per_window=2)

    snap = TaskSnapshot(task_id="task-1", prompt="x")
    r1 = svc.on_exhaustion(agent_id="a", tenant_id="t1", current_account_id="cx-0", snapshot=snap, now=_now())
    r2 = svc.on_exhaustion(agent_id="a", tenant_id="t1", current_account_id=r1.to_account, snapshot=snap, now=_now())
    r3 = svc.on_exhaustion(agent_id="a", tenant_id="t1", current_account_id=r2.to_account, snapshot=snap, now=_now())

    assert r1.rotated and r2.rotated
    assert r3.rotated is False and r3.parked is True  # capped


def test_resume_hook_invoked_on_success():
    pool = AccountPool()
    pool.register(_acct("cx-1", "codex"))
    pool.register(_acct("op-1", "opus"))
    pool.lease("cx-1", "agent-X")
    resumed: list[str] = []
    svc = AccountRotationService(
        pool, FakeAuthenticator(),
        resume_hook=lambda account, snapshot: resumed.append(f"{account.account_id}:{snapshot.task_id}"),
    )
    svc.on_exhaustion(
        agent_id="agent-X", tenant_id="t1", current_account_id="cx-1",
        snapshot=TaskSnapshot(task_id="task-1", prompt="x"), now=_now(),
    )
    assert resumed == ["op-1:task-1"]



# ---- reset-time parsing -----------------------------------------------------
def test_parse_reset_time_relative():
    d = QuotaExhaustionDetector()
    out = d.parse_reset_time("4 days 2 hours 46 minutes", now=_now())
    assert out == _now() + timedelta(days=4, hours=2, minutes=46)


def test_parse_reset_time_clock_next_occurrence():
    d = QuotaExhaustionDetector()
    # now=12:00 UTC; "3:51 PM" -> same day 15:51
    out = d.parse_reset_time("3:51 PM", now=_now())
    assert out == _now().replace(hour=15, minute=51, second=0, microsecond=0)
    # "6am (Asia/Seoul)" -> tz stripped, next day 06:00 (already past 12:00)
    out2 = d.parse_reset_time("6am (Asia/Seoul)", now=_now())
    assert out2 == (_now().replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1))


def test_parse_reset_time_absolute_datetime():
    d = QuotaExhaustionDetector()
    out = d.parse_reset_time("2/1/2026, 3:36:33 PM", now=_now())
    assert out is not None and out.hour == 15 and out.day == 1 and out.month == 2


def test_parse_reset_time_unparseable_returns_none():
    d = QuotaExhaustionDetector()
    assert d.parse_reset_time("soon-ish", now=_now()) is None


# ---- DeviceLoginAuthenticator (fake service) --------------------------------
class _FakeSession:
    def __init__(self, session_id, status):
        self.session_id = session_id
        self.status = status


class _FakeResult:
    def __init__(self, session):
        self.session = session


class _FakeDeviceLoginService:
    """Emulates sessions_api.DeviceLoginService.start()/status()."""

    def __init__(self, statuses):
        self._statuses = list(statuses)  # sequence returned by successive status() calls
        self.started = []

    def start(self, seat_id):
        self.started.append(seat_id)
        return _FakeResult(_FakeSession(f"sess-{seat_id}", "pending"))

    def status(self, session_id):
        status = self._statuses.pop(0) if self._statuses else "active"
        return _FakeSession(session_id, status)


def test_authenticator_login_and_wait_success():
    from rotation import DeviceLoginAuthenticator

    svc = _FakeDeviceLoginService(statuses=["pending", "active"])
    auth = DeviceLoginAuthenticator(svc, poll_interval_s=0, sleep=lambda s: None)
    acc = _acct("cx-1", "codex")
    sid = auth.login(acc)
    assert sid == "sess-seat-cx-1"
    assert auth.wait_authenticated(sid, timeout_s=5) is True


def test_authenticator_wait_fails_on_degraded():
    from rotation import DeviceLoginAuthenticator

    svc = _FakeDeviceLoginService(statuses=["degraded"])
    auth = DeviceLoginAuthenticator(svc, poll_interval_s=0, sleep=lambda s: None)
    assert auth.wait_authenticated("sess-x", timeout_s=5) is False


def test_authenticator_logout_noop_without_command():
    from rotation import DeviceLoginAuthenticator

    auth = DeviceLoginAuthenticator(_FakeDeviceLoginService([]), logout_commands={})
    # no command configured -> safe no-op, must not raise
    auth.logout(_acct("cx-1", "codex"))


# ---- assembly loader --------------------------------------------------------
def test_build_account_pool_from_records():
    from rotation import build_account_pool

    pool = build_account_pool([
        {"seat_id": "s1", "tenant_id": "t1", "vendor": "codex", "home_dir": "/srv/s1", "tokens_per_window": 500000},
        {"seat_id": "s2", "tenant_id": "t1", "vendor": "opus", "home_dir": "/srv/s2"},
    ])
    chosen = pool.select_next(None, "t1", now=_now())
    assert chosen.account_id == "s1"  # codex priority
    assert pool.get("s2").window_seconds == 18000  # default 5h


def test_account_from_record_requires_fields():
    from rotation import account_from_record

    try:
        account_from_record({"seat_id": "s1", "vendor": "codex"})  # missing tenant_id/home_dir
    except ValueError as exc:
        assert "missing fields" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")



# ---- trigger: exhaustion_from_event -----------------------------------------
def test_detect_any_finds_vendor_without_hint():
    d = QuotaExhaustionDetector()
    sig = d.detect_any("Claude usage limit reached. Your limit will reset at 2pm")
    assert sig.exhausted and sig.vendor in {"opus", "claude"}


def test_exhaustion_from_event_text_in_message():
    from rotation import exhaustion_from_event

    d = QuotaExhaustionDetector()
    event = {"message": "You've hit your usage limit, try again at 3:51 PM", "details": {}}
    sig = exhaustion_from_event(d, event)
    assert sig.exhausted and sig.vendor == "codex"


def test_exhaustion_from_event_queue_429():
    from rotation import exhaustion_from_event

    d = QuotaExhaustionDetector()
    event = {"message": "", "details": {"status_code": 429}}
    assert exhaustion_from_event(d, event, vendor="codex").exhausted


def test_exhaustion_from_event_503_not_exhausted():
    from rotation import exhaustion_from_event

    d = QuotaExhaustionDetector()
    event = {"message": "", "details": {"queue": {"status_code": 503, "message": "high traffic"}}}
    sig = exhaustion_from_event(d, event, vendor="antigravity")
    assert not sig.exhausted


def test_exhaustion_from_event_no_signal():
    from rotation import exhaustion_from_event

    d = QuotaExhaustionDetector()
    event = {"message": "working fine", "details": {"queue": {"state": "in_progress"}}}
    assert not exhaustion_from_event(d, event).exhausted

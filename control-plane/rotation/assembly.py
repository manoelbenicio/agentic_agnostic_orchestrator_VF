"""Assembly helpers to build the rotation stack from configuration.

Deploy-ready wiring: load accounts from the same seat records already used by the
control plane (``AOP_SEATS_JSON`` / ``AOP_SEATS_FILE``), enriched with rotation
fields (``priority``, ``tokens_per_window``, ``window_seconds``, ``auth_mode``).
"""

from __future__ import annotations

from typing import Any

from .auth import DeviceLoginAuthenticator
from .models import Account, WINDOW_SECONDS_5H
from .pool import AccountPool
from .service import AccountRotationService, ResumeHook


def account_from_record(record: dict[str, Any]) -> Account:
    """Build an Account from a seat/account config record.

    Required: seat_id, tenant_id, vendor, home_dir. Optional rotation fields
    default sensibly (5h window, priority derived from vendor expertise).
    """
    required = {"seat_id", "tenant_id", "vendor", "home_dir"}
    missing = required - record.keys()
    if missing:
        raise ValueError(f"account record missing fields: {sorted(missing)}")
    config_dir = str(record.get("config_dir") or f"{record['home_dir']}/.config")
    return Account(
        account_id=str(record.get("account_id") or record["seat_id"]),
        vendor=str(record["vendor"]),
        tenant_id=str(record["tenant_id"]),
        seat_id=str(record["seat_id"]),
        home_dir=str(record["home_dir"]),
        config_dir=config_dir,
        auth_mode=str(record.get("auth_mode", "device")),
        priority=int(record["priority"]) if record.get("priority") is not None else None,
        tokens_per_window=int(record.get("tokens_per_window", 0)),
        window_seconds=int(record.get("window_seconds", WINDOW_SECONDS_5H)),
    )


def build_account_pool(records: list[dict[str, Any]]) -> AccountPool:
    """Build an AccountPool from a list of seat/account records."""
    pool = AccountPool()
    for record in records:
        pool.register(account_from_record(record))
    return pool


def build_rotation_service(
    records: list[dict[str, Any]],
    device_login_service: Any,
    *,
    resume_hook: ResumeHook | None = None,
    logout_commands: dict[str, str] | None = None,
    login_timeout_s: float = 120.0,
    max_rotations_per_window: int = 8,
) -> AccountRotationService:
    """Assemble a ready-to-use AccountRotationService.

    ``device_login_service`` is the live ``sessions_api.DeviceLoginService``.
    Wire ``resume_hook`` to re-dispatch the task on the new account.
    """
    pool = build_account_pool(records)
    authenticator = DeviceLoginAuthenticator(
        device_login_service,
        logout_commands=logout_commands,
    )
    return AccountRotationService(
        pool,
        authenticator,
        resume_hook=resume_hook,
        login_timeout_s=login_timeout_s,
        max_rotations_per_window=max_rotations_per_window,
    )

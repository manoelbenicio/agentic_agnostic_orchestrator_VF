"""Authentication adapter for rotation (logout/login of a vendor account).

Wraps the existing ``sessions_api.DeviceLoginService`` (device-login / OAuth only
— doc 36 §7). Decoupled via Protocol so rotation can be tested with a fake.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time as _time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .models import Account

logger = logging.getLogger(__name__)

# Session statuses that mean "logged in and usable".
_AUTHENTICATED = {"active", "authenticated", "connected", "ready"}
_TERMINAL_FAIL = {"degraded", "expired", "failed", "error"}


class AccountAuthenticator(Protocol):
    """Boundary the rotation service depends on for switching credentials."""

    def logout(self, account: Account) -> None: ...
    def login(self, account: Account) -> str: ...
    def wait_authenticated(self, session_id: str, *, timeout_s: float) -> bool: ...


class DeviceLoginAuthenticator:
    """Adapter over ``sessions_api.DeviceLoginService`` (duck-typed).

    - ``login``  → ``service.start(account.seat_id)`` → returns the session id.
    - ``wait_authenticated`` → polls ``service.status(session_id)`` until the
      session is authenticated, terminally failed, or the timeout elapses.
    - ``logout`` → runs a configurable per-vendor logout command in the account's
      isolated env (``HOME``/config dir). Device-login/OAuth only; if no command
      is configured for the vendor it is a safe no-op (best-effort).

    ``logout_commands`` may be loaded from ``AOP_LOGOUT_COMMANDS_JSON`` (a JSON
    object {vendor: command}). ``sleep``/``clock`` are injectable for tests.
    """

    def __init__(
        self,
        device_login_service: Any,
        *,
        logout_commands: dict[str, str] | None = None,
        poll_interval_s: float = 2.0,
        sleep: Callable[[float], None] = _time.sleep,
        clock: Callable[[], float] = _time.monotonic,
    ) -> None:
        self._svc = device_login_service
        self._logout_commands = logout_commands if logout_commands is not None else self._commands_from_env()
        self._poll_interval_s = poll_interval_s
        self._sleep = sleep
        self._clock = clock

    @staticmethod
    def _commands_from_env() -> dict[str, str]:
        import json

        raw = os.environ.get("AOP_LOGOUT_COMMANDS_JSON")
        if not raw:
            return {}
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("AOP_LOGOUT_COMMANDS_JSON must be a JSON object {vendor: command}")
        return {str(k): str(v) for k, v in decoded.items() if v}

    def login(self, account: Account) -> str:
        """Start device-login for the account's seat; return the session id."""
        result = self._svc.start(account.seat_id)
        session = getattr(result, "session", result)
        session_id = getattr(session, "session_id", None)
        if not session_id:
            raise RuntimeError(f"device-login returned no session id for seat {account.seat_id}")
        return str(session_id)

    def wait_authenticated(self, session_id: str, *, timeout_s: float) -> bool:
        """Poll the session until authenticated / failed / timeout."""
        deadline = self._clock() + timeout_s
        while True:
            session = self._svc.status(session_id)
            status = (getattr(session, "status", None) or "").lower()
            if status in _AUTHENTICATED:
                return True
            if status in _TERMINAL_FAIL:
                return False
            if self._clock() >= deadline:
                return False
            self._sleep(self._poll_interval_s)

    def logout(self, account: Account) -> None:
        """Run the configured per-vendor logout command in isolated env."""
        command = self._logout_commands.get(account.vendor.lower())
        if not command:
            logger.info("no logout command configured for vendor %s; skipping (best-effort)", account.vendor)
            return
        env = os.environ.copy()
        env.update(
            {
                "HOME": account.home_dir,
                "XDG_CONFIG_HOME": account.config_dir,
                "AOP_SEAT_ID": account.seat_id,
                "AOP_SEAT_VENDOR": account.vendor,
            }
        )
        Path(account.home_dir).expanduser().mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            subprocess.run(shlex.split(command), check=False, capture_output=True, text=True, timeout=30, env=env)
        except Exception:  # logout must never block rotation
            logger.warning("logout command failed for account %s", account.account_id, exc_info=True)

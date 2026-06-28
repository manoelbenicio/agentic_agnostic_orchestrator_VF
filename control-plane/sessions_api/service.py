"""Vendor device-login service with explicit degraded states."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from seats_api.repository import SeatsRepository

from .repository import SessionRecord, SessionsRepository


@dataclass(frozen=True, slots=True)
class DeviceLoginResult:
    session: SessionRecord
    degraded: bool


class DeviceLoginService:
    def __init__(
        self,
        seats_repo: SeatsRepository,
        sessions_repo: SessionsRepository,
        *,
        provider_commands: dict[str, str] | None = None,
    ) -> None:
        self.seats_repo = seats_repo
        self.sessions_repo = sessions_repo
        self.provider_commands = provider_commands or {}

    def start(self, seat_id: str) -> DeviceLoginResult:
        seat = self.seats_repo.get(seat_id)
        if seat is None:
            raise KeyError(seat_id)
        if not seat.active:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason="seat is inactive",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )

        command = self.provider_commands.get(seat.vendor)
        if not command:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason=f"device-login provider for {seat.vendor} is not configured",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )

        try:
            _prepare_isolated_paths(seat.home_dir, seat.config_dir)
        except ValueError as exc:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason=str(exc),
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )

        env = os.environ.copy()
        env.update(
            {
                "HOME": seat.home_dir,
                "XDG_CONFIG_HOME": seat.config_dir,
                "AOP_SEAT_ID": seat.seat_id,
                "AOP_SEAT_VENDOR": seat.vendor,
                "AOP_SEAT_CONFIG_DIR": seat.config_dir,
            }
        )
        env.update(_vendor_env(seat.vendor, seat.home_dir, seat.config_dir))
        try:
            args = shlex.split(command)
        except ValueError as exc:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason=f"provider command is invalid: {exc}",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )
        if not args:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason="provider command is empty",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if completed.returncode != 0:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason=_clean(completed.stderr) or f"provider command exited {completed.returncode}",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason="provider command did not return JSON device-login payload",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )
        if not isinstance(payload, dict) or not (payload.get("verification_uri") or payload.get("verification_url")):
            return DeviceLoginResult(
                self._record_degraded(
                    seat_id=seat.seat_id,
                    tenant_id=seat.tenant_id,
                    vendor=seat.vendor,
                    reason="provider command returned incomplete device-login payload",
                    metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir},
                ),
                degraded=True,
            )
        session = self.sessions_repo.create(
            SessionRecord(
                session_id=f"sess-{uuid4().hex}",
                seat_id=seat.seat_id,
                tenant_id=seat.tenant_id,
                vendor=seat.vendor,
                status="pending",
                status_reason="device login started by configured provider",
                verification_uri=payload.get("verification_uri") or payload.get("verification_url"),
                user_code=payload.get("user_code"),
                device_code_ref=payload.get("device_code_ref") or payload.get("device_code"),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 900))),
                metadata={"home_dir": seat.home_dir, "config_dir": seat.config_dir, "provider": "command"},
            )
        )
        return DeviceLoginResult(session, degraded=False)

    def status(self, session_id: str) -> SessionRecord | None:
        session = self.sessions_repo.get(session_id)
        if (
            session
            and session.status == "pending"
            and session.expires_at
            and session.expires_at <= datetime.now(timezone.utc)
        ):
            return self.sessions_repo.set_status(session_id, "expired", "device login expired") or session
        return session

    def renew(self, session_id: str) -> DeviceLoginResult:
        current = self.sessions_repo.get(session_id)
        if current is None:
            raise KeyError(session_id)
        command = self.provider_commands.get(current.vendor)
        if not command:
            updated = self.sessions_repo.set_status(
                session_id,
                "degraded",
                f"renew provider for {current.vendor} is not configured",
            )
            return DeviceLoginResult(updated or current, degraded=True)
        return self.start(current.seat_id)

    def _record_degraded(
        self,
        *,
        seat_id: str,
        tenant_id: str,
        vendor: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> SessionRecord:
        return self.sessions_repo.create(
            SessionRecord(
                session_id=f"sess-{uuid4().hex}",
                seat_id=seat_id,
                tenant_id=tenant_id,
                vendor=vendor,
                status="degraded",
                status_reason=reason,
                metadata=metadata,
            )
        )


def provider_commands_from_json(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("AOP_DEVICE_LOGIN_COMMANDS_JSON must be a JSON object")
    return {str(key): str(value) for key, value in decoded.items() if value}


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def _prepare_isolated_paths(home_dir: str, config_dir: str) -> None:
    home = Path(home_dir).expanduser()
    config = Path(config_dir).expanduser()
    if not home.is_absolute() or not config.is_absolute():
        raise ValueError("seat home_dir and config_dir must be absolute paths")
    home_resolved = home.resolve(strict=False)
    config_resolved = config.resolve(strict=False)
    if not _is_relative_to(config_resolved, home_resolved):
        raise ValueError("seat config_dir must be inside home_dir for isolation")
    home_resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_resolved.mkdir(mode=0o700, parents=True, exist_ok=True)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _vendor_env(vendor: str, home_dir: str, config_dir: str) -> dict[str, str]:
    normalized = vendor.lower()
    if normalized == "codex":
        return {"CODEX_HOME": config_dir}
    if normalized == "claude":
        return {"CLAUDE_CONFIG_DIR": config_dir}
    if normalized == "gemini":
        return {"GEMINI_CONFIG_DIR": config_dir}
    if normalized == "kiro":
        return {"KIRO_HOME": home_dir, "KIRO_CONFIG_DIR": config_dir}
    return {}

"""Automatic account rotation on token exhaustion.

Design: docs/30-COMPONENTES/36-ROTACAO-CONTAS-TOKEN.md · ADR-009.

Skeleton composing the existing building blocks:
  * seats.SeatPool        → credential isolation per account (home_dir/config_dir)
  * sessions_api.DeviceLoginService → device-login/OAuth (logout/login)
  * scheduler.QuotaLedger → 5h/weekly quota windows

This package is NOT yet wired into app.main/dependencies; it is the extension
surface for the rotation onda. Pure logic (priority selection, detection,
anti-thrash, parking) is implemented; runtime-coupled steps (logout/login/resume)
are explicit extension points.
"""

from __future__ import annotations

from .auth import AccountAuthenticator, DeviceLoginAuthenticator
from .assembly import account_from_record, build_account_pool, build_rotation_service
from .detector import DEFAULT_PATTERNS, ExhaustionSignal, QuotaExhaustionDetector
from .models import (
    Account,
    AccountStatus,
    RotationOutcome,
    RotationReason,
    TaskSnapshot,
    VENDOR_PRIORITY,
)
from .pool import AccountPool
from .service import AccountRotationService, ResumeHook
from .trigger import exhaustion_from_event

__all__ = [
    "Account",
    "AccountAuthenticator",
    "AccountPool",
    "AccountRotationService",
    "AccountStatus",
    "DEFAULT_PATTERNS",
    "DeviceLoginAuthenticator",
    "ExhaustionSignal",
    "QuotaExhaustionDetector",
    "ResumeHook",
    "RotationOutcome",
    "RotationReason",
    "TaskSnapshot",
    "VENDOR_PRIORITY",
    "account_from_record",
    "build_account_pool",
    "build_rotation_service",
    "exhaustion_from_event",
]

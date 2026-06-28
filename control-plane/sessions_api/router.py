"""FastAPI routes for vendor sessions and device-login."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .repository import SessionRecord, SessionsRepository
from .service import DeviceLoginService


router = APIRouter(prefix="/sessions", tags=["sessions"])
Vendor = Literal["codex", "claude", "gemini", "kiro"]


class DeviceLoginRequest(BaseModel):
    seat_id: str = Field(min_length=1)


def session_service(request: Request) -> DeviceLoginService:
    return request.app.state.container.session_service


def sessions_repository(request: Request) -> SessionsRepository:
    return request.app.state.container.sessions_repo


@router.post("/device-login", status_code=status.HTTP_202_ACCEPTED)
def start_device_login(payload: DeviceLoginRequest, service: DeviceLoginService = Depends(session_service)) -> dict[str, Any]:
    try:
        result = service.start(payload.seat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "seat_not_found", "seat_id": payload.seat_id}) from exc
    if result.degraded:
        raise HTTPException(
            status_code=503,
            detail={"code": "device_login_degraded", "session": _session(result.session)},
        )
    return {"session": _session(result.session)}


@router.get("")
def list_sessions(
    seat_id: str | None = None,
    tenant_id: str | None = None,
    vendor: Vendor | None = None,
    repo: SessionsRepository = Depends(sessions_repository),
) -> dict[str, Any]:
    return {"sessions": [_session(session) for session in repo.list(seat_id=seat_id, tenant_id=tenant_id, vendor=vendor)]}


@router.get("/{session_id}/status")
def get_status(session_id: str, service: DeviceLoginService = Depends(session_service)) -> dict[str, Any]:
    session = service.status(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "session_id": session_id})
    return {"session": _session(session)}


@router.post("/{session_id}/renew", status_code=status.HTTP_202_ACCEPTED)
def renew_session(session_id: str, service: DeviceLoginService = Depends(session_service)) -> dict[str, Any]:
    try:
        result = service.renew(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "session_id": session_id}) from exc
    if result.degraded:
        raise HTTPException(
            status_code=503,
            detail={"code": "session_renew_degraded", "session": _session(result.session)},
        )
    return {"session": _session(result.session)}


def _session(session: SessionRecord) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "seat_id": session.seat_id,
        "tenant_id": session.tenant_id,
        "vendor": session.vendor,
        "status": session.status,
        "status_reason": session.status_reason,
        "verification_uri": session.verification_uri,
        "user_code": session.user_code,
        "device_code_ref": session.device_code_ref,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        "metadata": session.metadata,
    }

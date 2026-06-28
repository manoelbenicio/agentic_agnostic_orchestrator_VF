"""FastAPI routes for persistent seats."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from .repository import SeatRecord, SeatsRepository
from sessions_api.repository import SessionsRepository


Vendor = Literal["codex", "claude", "gemini", "kiro"]

router = APIRouter(prefix="/seats", tags=["seats"])


class SeatCreateRequest(BaseModel):
    seat_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    vendor: Vendor
    home_dir: str = Field(min_length=1)
    config_dir: str = Field(min_length=1)
    display_name: str | None = None
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_isolated_paths(self) -> "SeatCreateRequest":
        _validate_isolated_paths(self.home_dir, self.config_dir)
        return self


class SeatUpdateRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=1)
    vendor: Vendor | None = None
    home_dir: str | None = Field(default=None, min_length=1)
    config_dir: str | None = Field(default=None, min_length=1)
    display_name: str | None = None
    active: bool | None = None
    metadata: dict[str, Any] | None = None


def seats_repository(request: Request) -> SeatsRepository:
    return request.app.state.container.seats_repo


def sessions_repository(request: Request) -> SessionsRepository:
    return request.app.state.container.sessions_repo


@router.post("", status_code=status.HTTP_201_CREATED)
def register_seat(
    payload: SeatCreateRequest,
    repo: SeatsRepository = Depends(seats_repository),
    sessions_repo: SessionsRepository = Depends(sessions_repository),
) -> dict[str, Any]:
    return {"seat": _seat(repo.upsert(SeatRecord(**payload.model_dump())), lease_count=0)}


@router.get("")
def list_seats(
    tenant_id: str | None = None,
    vendor: Vendor | None = None,
    repo: SeatsRepository = Depends(seats_repository),
    sessions_repo: SessionsRepository = Depends(sessions_repository),
) -> dict[str, Any]:
    lease_counts = sessions_repo.active_counts_by_seat()
    return {"seats": [_seat(seat, lease_count=lease_counts.get(seat.seat_id, 0)) for seat in repo.list(tenant_id=tenant_id, vendor=vendor)]}


@router.get("/{seat_id}")
def get_seat(
    seat_id: str,
    repo: SeatsRepository = Depends(seats_repository),
    sessions_repo: SessionsRepository = Depends(sessions_repository),
) -> dict[str, Any]:
    seat = repo.get(seat_id)
    if seat is None:
        raise HTTPException(status_code=404, detail={"code": "seat_not_found", "seat_id": seat_id})
    lease_count = sessions_repo.active_counts_by_seat().get(seat.seat_id, 0)
    return {"seat": _seat(seat, lease_count=lease_count)}


@router.patch("/{seat_id}")
def update_seat(
    seat_id: str,
    payload: SeatUpdateRequest,
    repo: SeatsRepository = Depends(seats_repository),
    sessions_repo: SessionsRepository = Depends(sessions_repository),
) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    current = repo.get(seat_id)
    if current is None:
        raise HTTPException(status_code=404, detail={"code": "seat_not_found", "seat_id": seat_id})
    _validate_isolated_paths(changes.get("home_dir", current.home_dir), changes.get("config_dir", current.config_dir))
    seat = repo.update(seat_id, changes)
    if seat is None:
        raise HTTPException(status_code=404, detail={"code": "seat_not_found", "seat_id": seat_id})
    lease_count = sessions_repo.active_counts_by_seat().get(seat.seat_id, 0)
    return {"seat": _seat(seat, lease_count=lease_count)}


@router.delete("/{seat_id}")
def remove_seat(seat_id: str, repo: SeatsRepository = Depends(seats_repository)) -> dict[str, Any]:
    if not repo.remove(seat_id):
        raise HTTPException(status_code=404, detail={"code": "seat_not_found", "seat_id": seat_id})
    return {"removed": True, "seat_id": seat_id}


def _seat(seat: SeatRecord, *, lease_count: int = 0) -> dict[str, Any]:
    return {
        "seat_id": seat.seat_id,
        "tenant_id": seat.tenant_id,
        "vendor": seat.vendor,
        "home_dir": seat.home_dir,
        "config_dir": seat.config_dir,
        "display_name": seat.display_name,
        "active": seat.active,
        "available": seat.active and lease_count == 0,
        "leased": lease_count > 0,
        "ref_count": lease_count,
        "metadata": seat.metadata,
    }


def _validate_isolated_paths(home_dir: str, config_dir: str) -> None:
    home = Path(home_dir).expanduser()
    config = Path(config_dir).expanduser()
    if not home.is_absolute() or not config.is_absolute():
        raise ValueError("home_dir and config_dir must be absolute paths")
    home_resolved = home.resolve(strict=False)
    config_resolved = config.resolve(strict=False)
    try:
        config_resolved.relative_to(home_resolved)
    except ValueError as exc:
        raise ValueError("config_dir must be inside home_dir") from exc

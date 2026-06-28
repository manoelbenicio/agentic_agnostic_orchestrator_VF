"""FastAPI routes for inbox events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from .models import InboxEventRecord, InboxEventType


class InboxEventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    type: InboxEventType = InboxEventType.INFO
    title: str = Field(min_length=1)
    message: str = ""


class InboxEventResponse(BaseModel):
    id: str
    tenant_id: str
    type: InboxEventType
    title: str
    message: str
    read: bool
    archived: bool
    created_at: datetime | None


class BulkArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_ids: list[str] = Field(min_length=1)


class UnreadCountResponse(BaseModel):
    count: int


def build_inbox_router(get_state: Callable[[], Any]) -> APIRouter:
    """Build the inbox router using the app state dependency."""
    router = APIRouter(prefix="/inbox", tags=["inbox"])

    def repository(state: Any = Depends(get_state)) -> Any:
        repo = getattr(state, "inbox_repo", None)
        if repo is None:
            raise HTTPException(status_code=503, detail="inbox repository unavailable")
        return repo

    @router.get("", response_model=list[InboxEventResponse])
    def list_events(
        tenant_id: str | None = None,
        read: bool | None = None,
        archived: bool = False,
        repo: Any = Depends(repository),
    ) -> list[InboxEventResponse]:
        return [
            _event(event)
            for event in repo.list(tenant_id=tenant_id, read=read, archived=archived)
        ]

    @router.post("", response_model=InboxEventResponse, status_code=status.HTTP_201_CREATED)
    def create_event(
        request: InboxEventCreateRequest,
        repo: Any = Depends(repository),
    ) -> InboxEventResponse:
        event = repo.create(
            tenant_id=request.tenant_id,
            type=request.type,
            title=request.title,
            message=request.message,
        )
        return _event(event)

    @router.post("/{event_id}/read", response_model=InboxEventResponse)
    def mark_read(
        event_id: str,
        repo: Any = Depends(repository),
    ) -> InboxEventResponse:
        event = repo.mark_read(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="inbox event not found")
        return _event(event)

    @router.post("/bulk-archive")
    def bulk_archive(
        request: BulkArchiveRequest,
        repo: Any = Depends(repository),
    ) -> dict[str, int]:
        count = repo.bulk_archive(request.event_ids)
        return {"archived_count": count}

    @router.get("/unread-count", response_model=UnreadCountResponse)
    def unread_count(
        tenant_id: str | None = None,
        repo: Any = Depends(repository),
    ) -> UnreadCountResponse:
        return UnreadCountResponse(count=repo.unread_count(tenant_id=tenant_id))

    return router


def _event(event: InboxEventRecord) -> InboxEventResponse:
    return InboxEventResponse(
        id=event.id,
        tenant_id=event.tenant_id,
        type=event.type,
        title=event.title,
        message=event.message,
        read=event.read,
        archived=event.archived,
        created_at=event.created_at,
    )

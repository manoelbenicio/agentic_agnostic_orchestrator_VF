"""Live WebSocket updates for provisioning dashboard events."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter(tags=["provisioning-live"])


class ProvisioningEvent(BaseModel):
    """JSON message sent to provisioning dashboard websocket clients."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConnectionManager:
    """Tracks active dashboard websocket clients and broadcasts JSON events."""

    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any] | ProvisioningEvent) -> None:
        if isinstance(message, ProvisioningEvent):
            payload = message.model_dump(mode="json")
        else:
            payload = _jsonable(message)

        async with self._lock:
            connections = tuple(self.active_connections)

        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self.active_connections.discard(websocket)

    async def broadcast_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        await self.broadcast(ProvisioningEvent(event_type=event_type, payload=payload or {}))


manager = ConnectionManager()


@router.websocket("/ws/provisioning/live")
async def provisioning_live_websocket(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json(
            ProvisioningEvent(event_type="connection.established", payload={"stream": "provisioning"}).model_dump(
                mode="json"
            )
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)


async def broadcast_provisioning_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    await manager.broadcast_event(event_type, payload)


def broadcast_provisioning_event_sync(event_type: str, payload: dict[str, Any] | None = None) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(broadcast_provisioning_event(event_type, payload))
        return
    loop.create_task(broadcast_provisioning_event(event_type, payload))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    return value

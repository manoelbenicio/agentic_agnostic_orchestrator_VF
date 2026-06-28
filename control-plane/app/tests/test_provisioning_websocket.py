from __future__ import annotations

import asyncio

from app.provisioning.websocket import ConnectionManager, ProvisioningEvent, router


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def test_connection_manager_connect_broadcast_disconnect() -> None:
    async def run() -> None:
        manager = ConnectionManager()
        websocket = FakeWebSocket()

        await manager.connect(websocket)  # type: ignore[arg-type]
        await manager.broadcast_event("new_request", {"request_id": "prov-1"})
        await manager.disconnect(websocket)  # type: ignore[arg-type]
        await manager.broadcast_event("activation_started", {"request_id": "prov-2"})

        assert websocket.accepted
        assert len(websocket.messages) == 1
        assert websocket.messages[0]["event_type"] == "new_request"
        assert websocket.messages[0]["payload"] == {"request_id": "prov-1"}
        assert "emitted_at" in websocket.messages[0]

    asyncio.run(run())


def test_provisioning_event_json_shape() -> None:
    payload = ProvisioningEvent(event_type="step_completed", payload={"step_name": "validation"}).model_dump(
        mode="json"
    )

    assert payload["event_type"] == "step_completed"
    assert payload["payload"] == {"step_name": "validation"}
    assert isinstance(payload["emitted_at"], str)


def test_websocket_route_is_registered() -> None:
    assert any(getattr(route, "path", None) == "/ws/provisioning/live" for route in router.routes)

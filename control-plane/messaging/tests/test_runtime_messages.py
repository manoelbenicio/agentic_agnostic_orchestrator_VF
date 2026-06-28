from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[2]
HERDMASTER_SRC = CONTROL_PLANE_ROOT.parents[1] / "HerdMaster" / "src"
for path in (CONTROL_PLANE_ROOT, HERDMASTER_SRC):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from app.main import create_app
from topology.mapper import CanvasEdge, CanvasNode


class FakeTopologyRepository:
    def __init__(self) -> None:
        self._db = {}

    def save_topology(self, squad_id: str, nodes: list, edges: list) -> None:
        self._db[squad_id] = {
            "nodes": [node.__dict__ for node in nodes],
            "edges": [edge.__dict__ for edge in edges],
        }

    def get_topology(self, squad_id: str):
        return self._db.get(squad_id)


class FakeTraceService:
    def __init__(self) -> None:
        self.events = []
        self._counter = 0

    def new_trace_id(self) -> str:
        self._counter += 1
        return f"trace-msg-{self._counter}"

    def record(self, **kwargs):
        event = SimpleNamespace(event_id=f"audit-{len(self.events) + 1}", **kwargs)
        self.events.append(event)
        return event


@dataclass
class FakeMessageBus:
    sent: list = field(default_factory=list)

    async def send(self, message) -> None:
        self.sent.append(message)


class FakeState(SimpleNamespace):
    def close(self) -> None:
        return None


def _state() -> SimpleNamespace:
    topology_repo = FakeTopologyRepository()
    topology_repo.save_topology(
        "squad-a",
        [
            CanvasNode("tl", "orchestrator"),
            CanvasNode("worker-a", "worker"),
            CanvasNode("worker-b", "worker"),
        ],
        [
            CanvasEdge("tl", "worker-a"),
            CanvasEdge("worker-a", "tl"),
            CanvasEdge("tl", "worker-b"),
            CanvasEdge("worker-b", "tl"),
        ],
    )
    state = FakeState(
        topology_repo=topology_repo,
        trace_service=FakeTraceService(),
        message_bus=FakeMessageBus(),
    )
    return state


def test_runtime_message_allowed_routes_through_message_bus() -> None:
    state = _state()

    with TestClient(create_app(state=state)) as client:
        response = client.post(
            "/squads/squad-a/messages",
            json={
                "operation": "send_message",
                "from_agent": "tl",
                "to_agent": "worker-a",
                "content": "status?",
                "trace_id": "trace-allowed",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["route"] == "herdmaster_message_bus"
    assert body["trace_id"] == "trace-allowed"
    assert len(state.message_bus.sent) == 1
    assert state.message_bus.sent[0].from_agent == "tl"
    assert state.message_bus.sent[0].to == "worker-a"
    assert state.trace_service.events[0].details["allowed"] is True


def test_runtime_message_lateral_denied_records_topology_violation_audit() -> None:
    state = _state()

    with TestClient(create_app(state=state)) as client:
        response = client.post(
            "/squads/squad-a/messages",
            json={
                "operation": "send_message",
                "from_agent": "worker-a",
                "to_agent": "worker-b",
                "content": "lateral",
                "trace_id": "trace-denied",
            },
        )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "topology_violation"
    assert detail["trace_id"] == "trace-denied"
    assert detail["from_agent"] == "worker-a"
    assert detail["to_agent"] == "worker-b"
    assert detail["audit_event_id"] == "audit-1"
    assert state.message_bus.sent == []
    assert state.trace_service.events[0].message == "runtime message blocked"
    assert state.trace_service.events[0].details["allowed"] is False
    assert state.trace_service.events[0].details["reason"] == "default policy deny"


def test_runtime_handoff_allowed_back_to_tech_lead() -> None:
    state = _state()

    with TestClient(create_app(state=state)) as client:
        response = client.post(
            "/squads/squad-a/messages",
            json={
                "operation": "handoff",
                "from_agent": "worker-a",
                "to_agent": "tl",
                "payload": {"summary": "blocked on dependency"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "handoff"
    assert body["trace_id"].startswith("trace-msg-")
    assert state.message_bus.sent[0].payload["operation"] == "handoff"


def test_runtime_message_degrades_explicitly_without_real_bus() -> None:
    state = _state()
    state.message_bus = None
    state.message_bus_status = {"status": "degraded", "last_error": "HerdMaster message bus unavailable"}

    with TestClient(create_app(state=state)) as client:
        response = client.post(
            "/squads/squad-a/messages",
            json={
                "operation": "send_message",
                "from_agent": "tl",
                "to_agent": "worker-a",
                "content": "status?",
                "trace_id": "trace-degraded",
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "message_bus_unavailable"
    assert detail["trace_id"] == "trace-degraded"
    assert detail["audit_event_id"] == "audit-1"
    assert state.trace_service.events[0].details["allowed"] is False
    assert state.trace_service.events[0].details["reason"] == "HerdMaster message bus unavailable"

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from squad_api import build_squad_router


class FakeTopologyRepository:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, list[dict[str, str]]]] = {}

    def save_topology(self, squad_id: str, nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> None:
        self.saved[squad_id] = {"nodes": nodes, "edges": edges}

    def get_topology(self, squad_id: str):
        return self.saved.get(squad_id)


def _client(repo: FakeTopologyRepository | None = None) -> TestClient:
    state = SimpleNamespace(topology_repo=repo or FakeTopologyRepository())
    app = FastAPI()
    app.include_router(build_squad_router(lambda: state))
    return TestClient(app)


def test_save_and_get_topology_return_stored_canvas_and_effective_acl() -> None:
    client = _client()

    saved = client.post(
        "/squads/squad-a/topology",
        json={
            "nodes": [
                {"id": "tl", "role": "tech-lead", "label": "Tech Lead", "x": "100", "y": "80"},
                {"id": "worker", "role": "worker", "label": "Worker"},
            ],
            "edges": [{"id": "edge-1", "source": "tl", "target": "worker"}],
        },
    )

    assert saved.status_code == 200
    body = saved.json()
    assert body["stored"]["nodes"][0] == {
        "id": "tl",
        "role": "orchestrator",
        "label": "Tech Lead",
        "x": "100",
        "y": "80",
    }
    assert body["stored"]["edges"] == [{"source": "tl", "target": "worker", "id": "edge-1"}]
    assert body["effective_topology"]["default_policy"] == "deny"
    tl_role = next(role for role in body["effective_topology"]["roles"] if role["agents"] == ["tl"])
    assert tl_role["can_dispatch_tasks"] is True
    assert tl_role["can_send_to"] == ["worker"]

    fetched = client.get("/squads/squad-a/topology")

    assert fetched.status_code == 200
    assert fetched.json() == body


def test_get_missing_topology_returns_empty_effective_acl_not_placeholder() -> None:
    response = _client().get("/squads/missing/topology")

    assert response.status_code == 200
    assert response.json() == {
        "squad_id": "missing",
        "stored": None,
        "effective_topology": {"default_policy": "deny", "roles": []},
    }


def test_invalid_edge_returns_422_instead_of_500() -> None:
    response = _client().post(
        "/squads/squad-a/topology",
        json={
            "nodes": [{"id": "tl", "role": "orchestrator"}],
            "edges": [{"source": "tl", "target": "missing"}],
        },
    )

    assert response.status_code == 422
    assert "does not match a topology node" in response.json()["detail"]

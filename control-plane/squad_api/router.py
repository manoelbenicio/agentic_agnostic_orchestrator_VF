"""FastAPI routes for squad topology management."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from topology.mapper import CanvasEdge, CanvasNode, TopologyMapper


class TopologyNodeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    role: str | None = None

    @field_validator("role")
    @classmethod
    def non_empty_role(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("role must not be empty")
        return value


class TopologyEdgeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class TopologySaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[TopologyNodeRequest]
    edges: list[TopologyEdgeRequest]


def build_squad_router(get_state: Callable[[], Any]) -> APIRouter:
    """Build routes for persisted squad topology and effective ACL."""
    router = APIRouter(prefix="/squads", tags=["squads"])

    def state_dep(state: Any = Depends(get_state)) -> Any:
        if getattr(state, "topology_repo", None) is None:
            raise HTTPException(status_code=503, detail="topology repository unavailable")
        return state

    @router.post("/{squad_id}/topology", status_code=status.HTTP_200_OK)
    def save_topology(
        squad_id: str,
        request: TopologySaveRequest,
        state: Any = Depends(state_dep),
    ) -> dict[str, Any]:
        try:
            nodes, edges = _canvas_topology(request.nodes, request.edges)
            effective = _effective_topology(nodes, edges)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        state.topology_repo.save_topology(squad_id, nodes, edges)
        return {"squad_id": squad_id, "stored": {"nodes": nodes, "edges": edges}, "effective_topology": effective}

    @router.get("/{squad_id}/topology")
    def get_topology(squad_id: str, state: Any = Depends(state_dep)) -> dict[str, Any]:
        stored = state.topology_repo.get_topology(squad_id)
        if stored is None:
            return {
                "squad_id": squad_id,
                "stored": None,
                "effective_topology": _effective_topology([], []),
            }
        try:
            nodes, edges = _canvas_topology(
                [TopologyNodeRequest.model_validate(item) for item in stored.get("nodes", [])],
                [TopologyEdgeRequest.model_validate(item) for item in stored.get("edges", [])],
            )
            effective = _effective_topology(nodes, edges)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"stored topology is invalid: {exc}") from exc
        return {"squad_id": squad_id, "stored": {"nodes": nodes, "edges": edges}, "effective_topology": effective}

    return router


def _canvas_topology(
    nodes: list[TopologyNodeRequest],
    edges: list[TopologyEdgeRequest],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    node_ids = {node.id for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("topology node ids must be unique")
    normalized_nodes = []
    for node in nodes:
        item = {key: str(value) for key, value in node.model_dump(mode="json", exclude_none=True).items()}
        item["role"] = _normalize_role(item.get("role"), node.id)
        normalized_nodes.append(item)

    normalized_edges = []
    for edge in edges:
        item = {key: str(value) for key, value in edge.model_dump(mode="json", exclude_none=True).items()}
        if item["source"] not in node_ids:
            raise ValueError(f"edge source {item['source']!r} does not match a topology node")
        if item["target"] not in node_ids:
            raise ValueError(f"edge target {item['target']!r} does not match a topology node")
        normalized_edges.append(item)
    return normalized_nodes, normalized_edges


def _normalize_role(role: str | None, node_id: str) -> str:
    raw = (role or "worker").strip().lower()
    if raw in {"orchestrator", "tech-lead", "tech_lead", "tl", "lead"}:
        return "orchestrator"
    if raw in {"worker", "agent", "system"}:
        return "worker"
    if raw == "peer_reviewer":
        return raw
    raise ValueError(f"unsupported role {role!r} for node {node_id!r}")


def _effective_topology(nodes: list[dict[str, str]], edges: list[dict[str, str]]) -> dict[str, Any]:
    acl = TopologyMapper.map_to_acl(
        [CanvasNode(id=node["id"], role=node["role"]) for node in nodes],
        [CanvasEdge(source=edge["source"], target=edge["target"]) for edge in edges],
    )
    return {
        "default_policy": acl.default_policy,
        "roles": [
            {
                "name": role.name,
                "agents": list(role.agents),
                "can_send_to": list(role.can_send_to),
                "can_receive_from": list(role.can_receive_from),
                "can_dispatch_tasks": bool(role.can_dispatch_tasks),
                "can_reassign_tasks": bool(role.can_reassign_tasks),
            }
            for role in acl.roles
        ],
    }

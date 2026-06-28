"""Validation logic for provisioning requests."""

from __future__ import annotations

from typing import Any
from topology.mapper import CanvasNode, CanvasEdge, TopologyValidator


SUPPORTED_ADAPTERS = {"codex", "gemini", "antigravity", "antigravity-gemini", "opus", "claude"}


def validate_provisioning_request(data: dict[str, Any], state: Any) -> list[str]:
    """Validate a provisioning request against state repositories and topology rules.
    
    Returns a list of error messages. If the list is empty, validation passed.
    """
    errors: list[str] = []

    tenant_id = data.get("tenant_id")
    project_id = data.get("project_id")

    # 1. Tenant/Project Scope Validation
    if not tenant_id:
        errors.append("tenant_id is required")
    elif not isinstance(tenant_id, str) or not tenant_id.strip():
        errors.append("tenant_id must be a non-empty string")

    if not project_id:
        errors.append("project_id is required")
    elif not isinstance(project_id, str) or not project_id.strip():
        errors.append("project_id must be a non-empty string")

    if tenant_id and project_id:
        if getattr(state, "projects_repo", None) is not None:
            project = state.projects_repo.get(project_id)
            if not project:
                errors.append(f"Project '{project_id}' not found")
            elif project.tenant_id != tenant_id:
                errors.append(f"Project tenant_id mismatch: expected '{project.tenant_id}', got '{tenant_id}'")
        else:
            errors.append("projects repository unavailable")

    # 2. Stable-Key Uniqueness
    stable_key = data.get("stable_key")
    if stable_key:
        if not isinstance(stable_key, str) or not stable_key.strip():
            errors.append("stable_key must be a non-empty string")
        elif tenant_id:
            if getattr(state, "registry_repo", None) is not None:
                existing_agent = state.registry_repo.find_by_stable_key(tenant_id, stable_key)
                if existing_agent:
                    errors.append(f"stable_key '{stable_key}' is already in use for tenant '{tenant_id}'")
            else:
                errors.append("registry repository unavailable")

    # 3. Seat Availability
    seat_id = data.get("seat_id")
    if seat_id:
        if not isinstance(seat_id, str) or not seat_id.strip():
            errors.append("seat_id must be a non-empty string")
        elif tenant_id:
            if getattr(state, "seats_repo", None) is not None:
                seat = state.seats_repo.get(seat_id)
                if not seat:
                    errors.append(f"Seat '{seat_id}' not found")
                else:
                    if not seat.active:
                        errors.append(f"Seat '{seat_id}' is not active")
                    if seat.tenant_id != tenant_id:
                        errors.append(f"Seat tenant_id mismatch: expected '{seat.tenant_id}', got '{tenant_id}'")
            else:
                errors.append("seats repository unavailable")

    # 4. Adapter Support
    adapter = data.get("adapter") or data.get("vendor") or data.get("assignee_runtime")
    if adapter:
        if not isinstance(adapter, str) or not adapter.strip():
            errors.append("adapter name must be a non-empty string")
        elif adapter.lower() not in SUPPORTED_ADAPTERS:
            errors.append(f"Unsupported adapter / vendor: '{adapter}'")

    # 5. Credential / Seat Reference
    credential_ref = data.get("credential_ref")
    if credential_ref:
        if not isinstance(credential_ref, str) or not credential_ref.strip():
            errors.append("credential_ref must be a non-empty string")
        # credential_ref should reference a valid active seat for the tenant if it is a seat-based reference
        elif tenant_id and getattr(state, "seats_repo", None) is not None:
            # check if credential_ref exists as a seat in seats_repo
            seat = state.seats_repo.get(credential_ref)
            if not seat:
                errors.append(f"Referenced credential/seat '{credential_ref}' not found")
            else:
                if not seat.active:
                    errors.append(f"Referenced credential/seat '{credential_ref}' is not active")
                if seat.tenant_id != tenant_id:
                    errors.append(f"Referenced credential/seat tenant_id mismatch: expected '{seat.tenant_id}', got '{tenant_id}'")

    # 6. Topology reachability and ACL implications
    topology = data.get("topology")
    if topology is not None:
        if not isinstance(topology, dict):
            errors.append("topology must be an object")
        else:
            nodes_raw = topology.get("nodes")
            edges_raw = topology.get("edges")
            if not isinstance(nodes_raw, list):
                errors.append("topology.nodes must be a list")
            if not isinstance(edges_raw, list):
                errors.append("topology.edges must be a list")

            if isinstance(nodes_raw, list) and isinstance(edges_raw, list):
                # Map to CanvasNode and CanvasEdge
                canvas_nodes: list[CanvasNode] = []
                canvas_edges: list[CanvasEdge] = []
                node_ids: set[str] = set()
                has_orchestrator = False

                for i, node in enumerate(nodes_raw):
                    if not isinstance(node, dict):
                        errors.append(f"topology.nodes[{i}] must be an object")
                        continue
                    n_id = node.get("id")
                    role = node.get("role")
                    if not n_id or not isinstance(n_id, str):
                        errors.append(f"topology.nodes[{i}].id must be a non-empty string")
                        continue
                    if not role or not isinstance(role, str):
                        errors.append(f"topology.nodes[{i}].role must be a non-empty string")
                        continue
                    
                    if n_id in node_ids:
                        errors.append(f"Duplicate node id found in topology: '{n_id}'")
                    node_ids.add(n_id)

                    normalized_role = _normalize_role(role)
                    if normalized_role == "orchestrator":
                        has_orchestrator = True
                    canvas_nodes.append(CanvasNode(id=n_id, role=normalized_role))

                for i, edge in enumerate(edges_raw):
                    if not isinstance(edge, dict):
                        errors.append(f"topology.edges[{i}] must be an object")
                        continue
                    source = edge.get("source")
                    target = edge.get("target")
                    if not source or not isinstance(source, str):
                        errors.append(f"topology.edges[{i}].source must be a non-empty string")
                        continue
                    if not target or not isinstance(target, str):
                        errors.append(f"topology.edges[{i}].target must be a non-empty string")
                        continue

                    if source not in node_ids:
                        errors.append(f"topology.edges[{i}].source '{source}' does not match any node")
                    if target not in node_ids:
                        errors.append(f"topology.edges[{i}].target '{target}' does not match any node")

                    canvas_edges.append(CanvasEdge(source=source, target=target))

                # If no orchestrator is present, topology has ACL dispatch implications
                if len(canvas_nodes) > 0 and not has_orchestrator:
                    errors.append("Topology must contain at least one 'orchestrator' node to allow task dispatching")

                # Validate reachability
                try:
                    TopologyValidator.validate(canvas_nodes, canvas_edges)
                except ValueError as exc:
                    errors.append(str(exc))

    return errors


def _normalize_role(role: str) -> str:
    raw = role.strip().lower()
    if raw in {"orchestrator", "tech-lead", "tech_lead", "tl", "lead"}:
        return "orchestrator"
    if raw in {"worker", "agent", "system"}:
        return "worker"
    if raw == "peer_reviewer":
        return raw
    return "worker"

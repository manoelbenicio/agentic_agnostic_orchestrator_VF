from __future__ import annotations

from types import SimpleNamespace
import pytest
from app.provisioning import validate_provisioning_request
from registry.models import AgentRecord, AgentStatus
from seats_api.repository import SeatRecord
from projects_api.models import ProjectRecord, ProjectStatus


class FakeProjectRepository:
    def __init__(self, projects: dict[str, ProjectRecord]):
        self.projects = projects

    def get(self, project_id: str) -> ProjectRecord | None:
        return self.projects.get(project_id)


class FakeRegistryRepository:
    def __init__(self, agents: dict[str, AgentRecord]):
        self.agents = agents

    def find_by_stable_key(self, tenant_id: str, stable_key: str) -> AgentRecord | None:
        for agent in self.agents.values():
            if agent.tenant_id == tenant_id and agent.stable_key == stable_key:
                return agent
        return None


class FakeSeatsRepository:
    def __init__(self, seats: dict[str, SeatRecord]):
        self.seats = seats

    def get(self, seat_id: str) -> SeatRecord | None:
        return self.seats.get(seat_id)


@pytest.fixture
def fake_state():
    projects = {
        "project-a": ProjectRecord(
            project_id="project-a",
            tenant_id="tenant-a",
            name="Project A",
            description=None,
            status=ProjectStatus.ACTIVE,
            metadata={},
        )
    }
    
    agents = {
        "agent-1": AgentRecord(
            agent_id="agent-1",
            tenant_id="tenant-a",
            label="Agent 1",
            vendor="codex",
            role="worker",
            status=AgentStatus.ACTIVE,
            workspace_id="w",
            pane_id="p",
            stable_key="unique-key",
            metadata={},
        )
    }
    
    seats = {
        "seat-a": SeatRecord(
            seat_id="seat-a",
            tenant_id="tenant-a",
            vendor="codex",
            home_dir="/home/seat-a",
            config_dir="/config/seat-a",
            display_name=None,
            active=True,
            metadata={},
        ),
        "seat-inactive": SeatRecord(
            seat_id="seat-inactive",
            tenant_id="tenant-a",
            vendor="codex",
            home_dir="/home/seat-i",
            config_dir="/config/seat-i",
            display_name=None,
            active=False,
            metadata={},
        ),
    }

    return SimpleNamespace(
        projects_repo=FakeProjectRepository(projects),
        registry_repo=FakeRegistryRepository(agents),
        seats_repo=FakeSeatsRepository(seats),
    )


def test_validation_passes_for_valid_request(fake_state):
    data = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "stable_key": "new-unique-key",
        "seat_id": "seat-a",
        "adapter": "codex",
        "credential_ref": "seat-a",
        "topology": {
            "nodes": [
                {"id": "tl", "role": "orchestrator"},
                {"id": "w1", "role": "worker"},
            ],
            "edges": [
                {"source": "tl", "target": "w1"}
            ]
        }
    }
    errors = validate_provisioning_request(data, fake_state)
    assert errors == []


def test_validation_detects_project_not_found(fake_state):
    data = {
        "tenant_id": "tenant-a",
        "project_id": "non-existent-project",
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "Project 'non-existent-project' not found" in errors


def test_validation_detects_project_tenant_mismatch(fake_state):
    # project-a belongs to tenant-a, not tenant-b
    data = {
        "tenant_id": "tenant-b",
        "project_id": "project-a",
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "Project tenant_id mismatch" in errors[0]


def test_validation_detects_duplicate_stable_key(fake_state):
    data = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "stable_key": "unique-key", # already in use by agent-1
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "stable_key 'unique-key' is already in use" in errors[0]


def test_validation_detects_inactive_or_mismatched_seat(fake_state):
    # test seat not found
    data = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "seat_id": "seat-missing",
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "Seat 'seat-missing' not found" in errors

    # test seat inactive
    data["seat_id"] = "seat-inactive"
    errors = validate_provisioning_request(data, fake_state)
    assert "Seat 'seat-inactive' is not active" in errors

    # test seat tenant mismatch
    fake_state.seats_repo.seats["seat-a"] = SeatRecord(
        seat_id="seat-a",
        tenant_id="tenant-other",
        vendor="codex",
        home_dir="/home/seat-a",
        config_dir="/config/seat-a",
        active=True,
    )
    data["seat_id"] = "seat-a"
    errors = validate_provisioning_request(data, fake_state)
    assert "Seat tenant_id mismatch" in errors[0]


def test_validation_detects_unsupported_adapter(fake_state):
    data = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "adapter": "unknown-adapter-123",
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "Unsupported adapter" in errors[0]


def test_validation_detects_invalid_topology(fake_state):
    # Worker node w1 is unreachable (no edges)
    data = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "topology": {
            "nodes": [
                {"id": "tl", "role": "orchestrator"},
                {"id": "w1", "role": "worker"},
            ],
            "edges": []
        }
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "worker w1 is unreachable" in errors[0]


def test_validation_detects_missing_orchestrator(fake_state):
    data = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "topology": {
            "nodes": [
                {"id": "w1", "role": "worker"},
            ],
            "edges": []
        }
    }
    errors = validate_provisioning_request(data, fake_state)
    assert "must contain at least one 'orchestrator' node" in errors[0]

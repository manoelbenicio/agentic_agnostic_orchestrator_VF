from __future__ import annotations

import pytest
import psycopg
from uuid import uuid4
from types import SimpleNamespace
from psycopg.rows import dict_row

from app.provisioning import ActivationResult, init_schema, orchestrate_activation, check_retry_eligibility
from registry.models import AgentRecord, AgentStatus
from seats_api.repository import SeatRecord
from projects_api.models import ProjectRecord, ProjectStatus
from conftest import _database_url


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


class FakeRegistryService:
    def __init__(self, repo: FakeRegistryRepository):
        self.repository = repo
        self.added = []

    def add_agent(self, **kwargs) -> AgentRecord:
        agent = AgentRecord(
            agent_id=kwargs.get("agent_id") or f"agent-{uuid4()}",
            tenant_id=kwargs["tenant_id"],
            label=kwargs["label"],
            vendor=kwargs["vendor"],
            role=kwargs["role"],
            status=AgentStatus.ACTIVE,
            stable_key=kwargs.get("stable_key"),
            metadata=kwargs.get("metadata") or {},
        )
        self.added.append(agent)
        return agent


class FakeSeatsRepository:
    def __init__(self, seats: dict[str, SeatRecord]):
        self.seats = seats
        self.updated = []

    def get(self, seat_id: str) -> SeatRecord | None:
        return self.seats.get(seat_id)

    def update(self, seat_id: str, changes: dict) -> SeatRecord:
        seat = self.get(seat_id)
        assert seat is not None
        updated_seat = SeatRecord(
            seat_id=seat.seat_id,
            tenant_id=seat.tenant_id,
            vendor=seat.vendor,
            home_dir=seat.home_dir,
            config_dir=seat.config_dir,
            display_name=changes.get("display_name", seat.display_name),
            active=changes.get("active", seat.active),
            metadata={**(seat.metadata or {}), **(changes.get("metadata") or {})},
        )
        self.updated.append((seat_id, changes))
        self.seats[seat_id] = updated_seat
        return updated_seat


class FakeTopologyRepository:
    def __init__(self):
        self.saved = []

    def save_topology(self, squad_id: str, nodes: list, edges: list):
        self.saved.append((squad_id, nodes, edges))


class FakeTraceService:
    def __init__(self):
        self.recorded = []

    def new_trace_id(self) -> str:
        return f"trace-{uuid4()}"

    def record(self, **kwargs):
        self.recorded.append(kwargs)
        return SimpleNamespace(event_id="test-event-id")


class FakeAuditRepository:
    def __init__(self):
        self.events = []

    def append(self, **kwargs) -> None:
        self.events.append(kwargs)


@pytest.fixture
def provisioning_db():
    database_url = _database_url()
    schema_name = f"provisioning_test_{uuid4().hex}"
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        init_schema(conn, schema_name=schema_name)
        
    yield database_url, schema_name
    
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        conn.commit()


def test_activation_orchestration_success(provisioning_db):
    database_url, schema_name = provisioning_db

    # Setup fake services
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
    
    agents = {}
    
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
    }

    projects_repo = FakeProjectRepository(projects)
    registry_repo = FakeRegistryRepository(agents)
    registry_service = FakeRegistryService(registry_repo)
    seats_repo = FakeSeatsRepository(seats)
    topology_repo = FakeTopologyRepository()
    trace_service = FakeTraceService()
    audit_repo = FakeAuditRepository()

    # Create Connection
    conn = psycopg.connect(database_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema_name}, public")
    
    state = SimpleNamespace(
        projects_repo=projects_repo,
        registry_repo=registry_repo,
        registry_service=registry_service,
        seats_repo=seats_repo,
        topology_repo=topology_repo,
        trace_service=trace_service,
        audit_repo=audit_repo,
        postgres_connections=[conn]
    )

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

    # Run activation
    res = orchestrate_activation(data, state)
    
    assert isinstance(res, ActivationResult)
    assert res["status"] == "completed"
    assert res["target"] == "new-unique-key"
    assert [step.status for step in res.step_results] == ["success"] * 5
    
    # 1. Verify seat update
    assert len(seats_repo.updated) == 1
    assert seats_repo.updated[0][0] == "seat-a"
    assert seats_repo.updated[0][1]["active"] is True
    assert seats_repo.updated[0][1]["metadata"]["provisioned_project_id"] == "project-a"
    
    # 2. Verify agent registry creation
    assert len(registry_service.added) == 2
    roles = {a.role for a in registry_service.added}
    assert "orchestrator" in roles
    assert "worker" in roles
    
    # 3. Verify topology save
    assert len(topology_repo.saved) == 1
    assert topology_repo.saved[0][0] == "project-a" # squad_id defaults to project_id
    assert len(topology_repo.saved[0][1]) == 2
    
    # 4. Verify tracing and audit hook call
    assert len(trace_service.recorded) == 1
    assert trace_service.recorded[0]["project_id"] == "project-a"
    assert trace_service.recorded[0]["tenant_id"] == "tenant-a"
    assert len(audit_repo.events) == 1
    assert audit_repo.events[0]["action"] == "provisioning.activation"
    
    # 5. Verify local provisioning logs in DB
    with conn.cursor() as cur:
        cur.execute("SELECT status, target FROM provisioning_records WHERE record_id = %s", (res["record_id"],))
        record = cur.fetchone()
        assert record is not None
        assert record["status"] == "completed"
        assert record["target"] == "new-unique-key"
        
        cur.execute("SELECT step_name, status FROM step_results WHERE record_id = %s ORDER BY started_at", (res["record_id"],))
        steps = cur.fetchall()
        assert len(steps) == 5
        step_names = [s["step_name"] for s in steps]
        assert "validation" in step_names
        assert "seats_activation" in step_names
        assert "registry_enrollment" in step_names
        assert "topology_configuration" in step_names
        assert "tracing_and_audit" in step_names
        
        for s in steps:
            assert s["status"] == "success"

    conn.close()


def test_activation_orchestration_validation_failure(provisioning_db):
    database_url, schema_name = provisioning_db

    # Empty repos to trigger validation failures
    projects_repo = FakeProjectRepository({})
    registry_repo = FakeRegistryRepository({})
    registry_service = FakeRegistryService(registry_repo)
    seats_repo = FakeSeatsRepository({})
    topology_repo = FakeTopologyRepository()
    trace_service = FakeTraceService()

    conn = psycopg.connect(database_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema_name}, public")
    
    state = SimpleNamespace(
        projects_repo=projects_repo,
        registry_repo=registry_repo,
        registry_service=registry_service,
        seats_repo=seats_repo,
        topology_repo=topology_repo,
        trace_service=trace_service,
        postgres_connections=[conn]
    )

    data = {
        "tenant_id": "tenant-a",
        "project_id": "non-existent-project",
    }

    # Should raise error
    with pytest.raises(ValueError) as excinfo:
        orchestrate_activation(data, state)
        
    assert "Validation failed" in str(excinfo.value)

    # Verify DB contains a failed record and step
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM provisioning_records")
        record = cur.fetchone()
        assert record is not None
        assert record["status"] == "failed"
        
        cur.execute("SELECT step_name, status, error FROM step_results")
        step = cur.fetchone()
        assert step is not None
        assert step["step_name"] == "validation"
        assert step["status"] == "failed"
        assert "Project 'non-existent-project' not found" in step["error"]

    conn.close()


def test_activation_retry_flow(provisioning_db):
    database_url, schema_name = provisioning_db

    # Setup fake services
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
    
    agents = {}
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
    }

    class FailingRegistryService(FakeRegistryService):
        def __init__(self, repo):
            super().__init__(repo)
            self.should_fail = True

        def add_agent(self, **kwargs) -> AgentRecord:
            if self.should_fail:
                raise RuntimeError("Registry service connection failed")
            return super().add_agent(**kwargs)

    projects_repo = FakeProjectRepository(projects)
    registry_repo = FakeRegistryRepository(agents)
    registry_service = FailingRegistryService(registry_repo)
    seats_repo = FakeSeatsRepository(seats)
    topology_repo = FakeTopologyRepository()
    trace_service = FakeTraceService()

    conn = psycopg.connect(database_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema_name}, public")
    
    state = SimpleNamespace(
        projects_repo=projects_repo,
        registry_repo=registry_repo,
        registry_service=registry_service,
        seats_repo=seats_repo,
        topology_repo=topology_repo,
        trace_service=trace_service,
        postgres_connections=[conn]
    )

    record_id = f"prov-retry-{uuid4()}"
    data = {
        "record_id": record_id,
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

    # 1. Run activation - Registry step should fail
    with pytest.raises(RuntimeError) as excinfo:
        orchestrate_activation(data, state)
    assert "Registry service connection failed" in str(excinfo.value)

    # 2. Check DB state: status should be failed, registry_enrollment failed
    with conn.cursor() as cur:
        cur.execute("SELECT status, metadata FROM provisioning_records WHERE record_id = %s", (record_id,))
        record = cur.fetchone()
        assert record is not None
        assert record["status"] == "failed"
        assert record["metadata"]["failed_step"] == "registry_enrollment"
        assert "Registry service connection failed" in record["metadata"]["failed_error"]

        cur.execute("SELECT step_name, status FROM step_results WHERE record_id = %s ORDER BY started_at", (record_id,))
        steps = cur.fetchall()
        # validation, seats_activation succeeded; registry_enrollment failed.
        # Remaining steps not run.
        assert len(steps) == 3
        assert steps[0]["step_name"] == "validation" and steps[0]["status"] == "success"
        assert steps[1]["step_name"] == "seats_activation" and steps[1]["status"] == "success"
        assert steps[2]["step_name"] == "registry_enrollment" and steps[2]["status"] == "failed"

    # 3. Check retry eligibility - Should be eligible
    elig = check_retry_eligibility(record_id, state)
    assert elig["eligible"] is True
    assert elig["status"] == "failed"
    assert len(elig["failed_steps"]) == 1
    assert elig["failed_steps"][0]["step_name"] == "registry_enrollment"

    # 4. Fix registry service, and run retry activation
    registry_service.should_fail = False
    
    # Store current seat updates count (should be 1 because seats_activation succeeded in attempt 1)
    seat_updates_before = len(seats_repo.updated)
    assert seat_updates_before == 1

    # Retry orchestrate
    res = orchestrate_activation(data, state)
    assert res["status"] == "completed"

    # Verify that seats_activation was skipped on retry (no additional seat updates)
    assert len(seats_repo.updated) == seat_updates_before

    # Verify topology was saved
    assert len(topology_repo.saved) == 1

    # Verify trace recorded
    assert len(trace_service.recorded) == 1

    # Verify DB state: status should be completed, and all steps are success (failed step was deleted)
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM provisioning_records WHERE record_id = %s", (record_id,))
        record = cur.fetchone()
        assert record["status"] == "completed"

        cur.execute("SELECT step_name, status FROM step_results WHERE record_id = %s ORDER BY started_at", (record_id,))
        steps = cur.fetchall()
        # Should now have 5 successful steps
        assert len(steps) == 5
        for s in steps:
            assert s["status"] == "success"

    # 5. Check retry eligibility again - Should be ineligible
    elig = check_retry_eligibility(record_id, state)
    assert elig["eligible"] is False
    assert "already completed" in elig["reason"]

    conn.close()

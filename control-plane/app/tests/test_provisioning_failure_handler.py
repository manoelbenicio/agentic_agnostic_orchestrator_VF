from __future__ import annotations

from types import SimpleNamespace

from app.provisioning import ActivationStepResult
from app.provisioning.failure_handler import (
    build_provisioning_failure_router,
    list_activation_failures,
    save_activation_failure,
)


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self.rows = []
        self.row = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params=()) -> None:
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT metadata FROM provisioning_records"):
            record = self.conn.records.get(params[0])
            self.row = {"metadata": record["metadata"]} if record else None
            return
        if normalized.startswith("UPDATE provisioning_records SET status"):
            status, metadata, record_id = params
            self.conn.records[record_id]["status"] = status
            self.conn.records[record_id]["metadata"] = _json_value(metadata)
            self.row = None
            return
        if normalized.startswith("INSERT INTO provisioning_records"):
            record_id, target, status, metadata = params
            self.conn.records[record_id] = {
                "record_id": record_id,
                "target": target,
                "status": status,
                "metadata": _json_value(metadata),
            }
            self.row = None
            return
        if normalized.startswith("SELECT record_id, target, metadata"):
            self.rows = [
                {
                    "record_id": record_id,
                    "target": record["target"],
                    "metadata": record["metadata"],
                }
                for record_id, record in self.conn.records.items()
                if record["status"] == "failed"
            ][: params[0]]
            return
        if normalized.startswith("SELECT step_name, status, output, error, duration_seconds"):
            self.rows = [step for step in self.conn.steps if step["record_id"] == params[0]]
            return
        raise AssertionError(f"unexpected query: {normalized}")

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self) -> None:
        self.records = {}
        self.steps = []
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_save_activation_failure_persists_retry_metadata() -> None:
    conn = FakeConnection()
    conn.records["rec-1"] = {
        "record_id": "rec-1",
        "target": "agent-a",
        "status": "running",
        "metadata": {"tenant_id": "tenant-1", "project_id": "project-1"},
    }
    state = SimpleNamespace(postgres_connections=[conn])

    failure = save_activation_failure(
        record_id="rec-1",
        target="agent-a",
        error=ValueError("boom"),
        failed_step="registry_enrollment",
        step_results=[
            ActivationStepResult(step_name="validation", status="success"),
            ActivationStepResult(step_name="registry_enrollment", status="failed", error="boom"),
        ],
        data={"tenant_id": "tenant-1", "project_id": "project-1", "stable_key": "agent-a"},
        state=state,
        base_backoff_seconds=1,
    )

    metadata = conn.records["rec-1"]["metadata"]
    assert conn.records["rec-1"]["status"] == "failed"
    assert failure.failed_step == "registry_enrollment"
    assert failure.retry_eligible is True
    assert metadata["failed_error"] == "boom"
    assert metadata["retry_count"] == 0
    assert metadata["next_retry_at"]
    assert metadata["step_results"][1]["status"] == "failed"


def test_provisioning_failures_list_failed_activations() -> None:
    conn = FakeConnection()
    conn.records["rec-1"] = {
        "record_id": "rec-1",
        "target": "agent-a",
        "status": "failed",
        "metadata": {
            "failed_step": "validation",
            "failed_error": "invalid request",
            "retry_eligible": True,
            "retry_count": 1,
            "max_retries": 3,
        },
    }
    conn.steps.append(
        {
            "record_id": "rec-1",
            "step_name": "validation",
            "status": "failed",
            "output": None,
            "error": "invalid request",
            "duration_seconds": 0.1,
        }
    )
    state = SimpleNamespace(postgres_connections=[conn])

    router = build_provisioning_failure_router(lambda: state)
    failures = list_activation_failures(state)

    assert any(route.path == "/provisioning/failures" for route in router.routes)
    assert failures[0].record_id == "rec-1"
    assert failures[0].failed_step == "validation"
    assert failures[0].step_results[0].status == "failed"


def _json_value(value):
    return getattr(value, "obj", value)

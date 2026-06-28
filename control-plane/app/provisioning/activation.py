"""Activation orchestration logic with failure handling and retry eligibility."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from app.provisioning.validation import validate_provisioning_request
from app.provisioning.websocket import broadcast_provisioning_event_sync


class ActivationStepResult(BaseModel):
    """Result for one activation orchestration step."""

    model_config = ConfigDict(extra="forbid")

    step_name: str
    status: str
    output: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0


class ActivationResult(BaseModel):
    """Activation orchestration result with per-step outcomes."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    status: str
    target: str
    step_results: list[ActivationStepResult] = Field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def orchestrate_activation(data: dict[str, Any], state: Any) -> ActivationResult:
    """Orchestrate the activation of a provisioning request.
    
    Validates the request first. If valid, proceeds with updating seats,
    registering agents, saving topology, and recording audits using the
    respective module services. Supports retrying previously failed activation
    runs by skipping already completed steps.
    """
    # 1. Resolve provisioning database connection
    conn = None
    if hasattr(state, "postgres_connections") and state.postgres_connections:
        conn = state.postgres_connections[-1]

    record_id = data.get("record_id") or f"prov-{uuid4()}"
    target = data.get("stable_key") or data.get("seat_id") or data.get("project_id") or "unknown"
    status = "running"
    metadata = dict(data)
    broadcast_provisioning_event_sync(
        "activation_started",
        {"record_id": record_id, "target": target, "status": status},
    )

    completed_steps: set[str] = set()
    step_results: list[ActivationStepResult] = []

    # 2. Check retry eligibility if record already exists
    if conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, metadata FROM provisioning_records WHERE record_id = %s",
                (record_id,),
            )
            row = cur.fetchone()
            if row:
                existing_status = row["status"]
                if existing_status == "completed":
                    raise ValueError(f"Activation record '{record_id}' is already completed and cannot be retried.")
                elif existing_status == "running":
                    raise ValueError(f"Activation record '{record_id}' is currently running.")

                # Fetch already completed steps
                cur.execute(
                    "SELECT step_name FROM step_results WHERE record_id = %s AND status = 'success'",
                    (record_id,),
                )
                for r in cur.fetchall():
                    completed_steps.add(r["step_name"])

                # Clean up failed/running steps from previous attempt
                cur.execute(
                    "DELETE FROM step_results WHERE record_id = %s AND status != 'success'",
                    (record_id,),
                )

                # Set status back to running
                cur.execute(
                    """
                    UPDATE provisioning_records
                    SET status = 'running', updated_at = CURRENT_TIMESTAMP
                    WHERE record_id = %s
                    """,
                    (record_id,),
                )
            else:
                # Insert initial provisioning record for new run
                cur.execute(
                    """
                    INSERT INTO provisioning_records (record_id, target, status, metadata)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (record_id, target, status, Jsonb(metadata)),
                )
        conn.commit()

    failed_step_name = None

    def run_step(step_name: str, func) -> Any:
        nonlocal failed_step_name
        if step_name in completed_steps:
            step_results.append(
                ActivationStepResult(
                    step_name=step_name,
                    status="skipped",
                    output=f"Skipped (already completed): {step_name}",
                )
            )
            return f"Skipped (already completed): {step_name}"

        step_id = f"step-{uuid4()}"
        started_at = datetime.now(timezone.utc)
        start_time = time.time()

        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO step_results (step_id, record_id, step_name, status, started_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (step_id, record_id, step_name, "running", started_at),
                )
            conn.commit()

        try:
            result_output = func()
            duration = time.time() - start_time
            completed_at = datetime.now(timezone.utc)

            if conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE step_results
                        SET status = %s, output = %s, duration_seconds = %s, completed_at = %s
                        WHERE step_id = %s
                        """,
                        ("success", str(result_output), duration, completed_at, step_id),
                    )
                conn.commit()
            step_results.append(
                ActivationStepResult(
                    step_name=step_name,
                    status="success",
                    output=str(result_output),
                    duration_seconds=duration,
                )
            )
            broadcast_provisioning_event_sync(
                "step_completed",
                {
                    "record_id": record_id,
                    "target": target,
                    "step_name": step_name,
                    "status": "success",
                    "duration_seconds": duration,
                },
            )
            return result_output
        except Exception as exc:
            failed_step_name = step_name
            duration = time.time() - start_time
            completed_at = datetime.now(timezone.utc)

            if conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE step_results
                        SET status = %s, error = %s, duration_seconds = %s, completed_at = %s
                        WHERE step_id = %s
                        """,
                        ("failed", str(exc), duration, completed_at, step_id),
                    )
                conn.commit()
            step_results.append(
                ActivationStepResult(
                    step_name=step_name,
                    status="failed",
                    error=str(exc),
                    duration_seconds=duration,
                )
            )
            broadcast_provisioning_event_sync(
                "step_completed",
                {
                    "record_id": record_id,
                    "target": target,
                    "step_name": step_name,
                    "status": "failed",
                    "error": str(exc),
                    "duration_seconds": duration,
                },
            )
            raise exc

    try:
        # Step 1: Validation
        def step_validation():
            errors = validate_provisioning_request(data, state)
            if errors:
                raise ValueError(f"Validation failed: {'; '.join(errors)}")
            return "Validation passed."

        run_step("validation", step_validation)

        # Step 2: Seats Activation
        def step_seats_activation():
            seat_id = data.get("seat_id")
            credential_ref = data.get("credential_ref")
            activated = []

            if seat_id and getattr(state, "seats_repo", None) is not None:
                seat = state.seats_repo.get(seat_id)
                if seat:
                    changes = {
                        "active": True,
                        "metadata": {
                            **(seat.metadata or {}),
                            "activated_at": datetime.now(timezone.utc).isoformat(),
                            "activation_status": "activated",
                            "provisioned_project_id": data.get("project_id"),
                        },
                    }
                    state.seats_repo.update(seat_id, changes)
                    activated.append(f"seat:{seat_id}")

            if credential_ref and credential_ref != seat_id and getattr(state, "seats_repo", None) is not None:
                cred_seat = state.seats_repo.get(credential_ref)
                if cred_seat:
                    changes = {
                        "active": True,
                        "metadata": {
                            **(cred_seat.metadata or {}),
                            "activated_at": datetime.now(timezone.utc).isoformat(),
                            "activation_status": "activated",
                            "provisioned_project_id": data.get("project_id"),
                        },
                    }
                    state.seats_repo.update(credential_ref, changes)
                    activated.append(f"credential:{credential_ref}")

            return f"Seats activated: {', '.join(activated)}" if activated else "No seats to activate."

        run_step("seats_activation", step_seats_activation)

        # Step 3: Registry Enrollment
        def step_registry_enrollment():
            tenant_id = data["tenant_id"]
            topology = data.get("topology")
            stable_key = data.get("stable_key")
            adapter = data.get("adapter") or data.get("vendor") or "codex"
            enrolled = []

            if topology and isinstance(topology, dict):
                nodes = topology.get("nodes") or []
                for node in nodes:
                    node_id = node.get("id")
                    role = node.get("role") or "worker"
                    node_stable_key = stable_key if (role == "orchestrator" and stable_key) else f"{tenant_id}-{node_id}"

                    if getattr(state, "registry_service", None) is not None:
                        existing = state.registry_service.repository.find_by_stable_key(tenant_id, node_stable_key)
                        if not existing:
                            agent = state.registry_service.add_agent(
                                tenant_id=tenant_id,
                                label=node_id,
                                vendor=adapter,
                                role=role,
                                stable_key=node_stable_key,
                                metadata=node.get("metadata"),
                            )
                            enrolled.append(agent.agent_id)
                        else:
                            enrolled.append(f"existing:{existing.agent_id}")
            elif stable_key:
                if getattr(state, "registry_service", None) is not None:
                    existing = state.registry_service.repository.find_by_stable_key(tenant_id, stable_key)
                    if not existing:
                        agent = state.registry_service.add_agent(
                            tenant_id=tenant_id,
                            label=data.get("label") or stable_key,
                            vendor=adapter,
                            role=data.get("role") or "worker",
                            stable_key=stable_key,
                            metadata=data.get("metadata"),
                        )
                        enrolled.append(agent.agent_id)
                    else:
                        enrolled.append(f"existing:{existing.agent_id}")

            return f"Enrolled agent(s): {', '.join(enrolled)}" if enrolled else "No agents to enroll."

        run_step("registry_enrollment", step_registry_enrollment)

        # Step 4: Topology Configuration
        def step_topology_configuration():
            topology = data.get("topology")
            if topology and isinstance(topology, dict) and getattr(state, "topology_repo", None) is not None:
                squad_id = data.get("squad_id") or data.get("project_id") or "squad-default"
                state.topology_repo.save_topology(squad_id, topology.get("nodes", []), topology.get("edges", []))
                return f"Topology saved for squad: {squad_id}"
            return "No topology configuration to save."

        run_step("topology_configuration", step_topology_configuration)

        # Step 5: Tracing and Audit Hooks
        def step_tracing_and_audit():
            from tracing import TraceLayer, TraceSignalType

            trace_id_val = data.get("trace_id") or f"trace-{uuid4()}"
            audit_written = False
            if getattr(state, "audit_repo", None) is not None:
                state.audit_repo.append(
                    user_id=str(data.get("user_id") or data.get("activated_by") or "system"),
                    action="provisioning.activation",
                    resource=str(data.get("stable_key") or data.get("seat_id") or data.get("project_id") or target),
                    trace_id=trace_id_val,
                )
                audit_written = True
            if getattr(state, "trace_service", None) is not None:
                state.trace_service.record(
                    trace_id=trace_id_val,
                    layer=TraceLayer.L2_CONTROL_PLANE,
                    signal_type=TraceSignalType.AUDIT,
                    tenant_id=data["tenant_id"],
                    project_id=data["project_id"],
                    issue_id=data.get("issue_id") or "issue-provisioning",
                    agent_id=data.get("stable_key") or "system",
                    runtime_id=data.get("adapter") or "system",
                    message="Provisioning activation orchestrated successfully",
                    details={
                        "record_id": record_id,
                        "target": target,
                        "stable_key": data.get("stable_key"),
                        "seat_id": data.get("seat_id"),
                        "adapter": data.get("adapter"),
                        "credential_ref": data.get("credential_ref"),
                        "has_topology": "topology" in data,
                        "audit_written": audit_written,
                    },
                )
                return f"Audit trace recorded with ID: {trace_id_val}; audit_written={audit_written}"
            return f"Tracing service unavailable; audit_written={audit_written}"

        run_step("tracing_and_audit", step_tracing_and_audit)

        # Update provisioning record to completed
        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE provisioning_records
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE record_id = %s
                    """,
                    ("completed", record_id),
                )
            conn.commit()

        result = ActivationResult(
            record_id=record_id,
            status="completed",
            target=target,
            step_results=step_results,
        )
        broadcast_provisioning_event_sync(
            "activation_succeeded",
            {"record_id": record_id, "target": target, "status": result.status},
        )
        return result

    except Exception as exc:
        from .failure_handler import save_activation_failure

        save_activation_failure(
            record_id=record_id,
            target=target,
            error=exc,
            failed_step=failed_step_name or "unknown",
            step_results=step_results,
            data=data,
            state=state,
        )
        broadcast_provisioning_event_sync(
            "activation_failed",
            {
                "record_id": record_id,
                "target": target,
                "status": "failed",
                "failed_step": failed_step_name or "unknown",
                "error": str(exc),
            },
        )
        raise exc


def check_retry_eligibility(record_id: str, state: Any) -> dict[str, Any]:
    """Check if a provisioning record is eligible for retry."""
    conn = None
    if hasattr(state, "postgres_connections") and state.postgres_connections:
        conn = state.postgres_connections[-1]

    if not conn:
        return {"eligible": False, "reason": "No database connection"}

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, metadata FROM provisioning_records WHERE record_id = %s",
            (record_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"eligible": False, "reason": f"Record '{record_id}' not found"}

        status = row["status"]
        metadata = row["metadata"] or {}

        if status == "completed":
            return {"eligible": False, "reason": "Activation is already completed"}

        if status == "failed":
            cur.execute(
                "SELECT step_name, error FROM step_results WHERE record_id = %s AND status = 'failed'",
                (record_id,),
            )
            failed_steps = cur.fetchall()
            failed_details = [
                {"step_name": f["step_name"], "error": f["error"]}
                for f in failed_steps
            ]
            return {
                "eligible": True,
                "status": "failed",
                "failed_steps": failed_details,
                "metadata": metadata,
            }

        return {"eligible": False, "reason": f"Record is in status '{status}'"}

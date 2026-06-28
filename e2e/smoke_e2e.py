#!/usr/bin/env python3
"""End-to-end smoke for the Agnostic Orchestration Platform control plane."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE = ROOT / "AOP" / "control-plane"
HERDMASTER_SRC = ROOT / "HerdMaster" / "src"
for path in (CONTROL_PLANE, HERDMASTER_SRC):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from herdmaster.acl.engine import AclEngine  # noqa: E402
from herdmaster.config import AclConfig, AclRole  # noqa: E402


BASE_URL = os.environ.get("AOP_E2E_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
OUT_DIR = Path(__file__).resolve().parent
EVIDENCE_PATH = OUT_DIR / "evidence.json"
REPORT_PATH = OUT_DIR / "REPORT.md"


class SmokeError(RuntimeError):
    """Raised when the E2E smoke flow fails."""


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SmokeError(f"{method} {path} failed: {exc}") from exc


def request_text(method: str, path: str) -> str:
    req = urllib.request.Request(f"{BASE_URL}{path}", method=method, headers={"Accept": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SmokeError(f"{method} {path} failed: {exc}") from exc


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise SmokeError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(value: Any, label: str) -> None:
    if not value:
        raise SmokeError(f"{label}: assertion failed")


def acl_from_effective(effective: dict[str, Any]) -> AclEngine:
    return AclEngine(
        AclConfig(
            default_policy=effective["default_policy"],
            roles=[
                AclRole(
                    name=role["name"],
                    agents=list(role["agents"]),
                    can_send_to=list(role["can_send_to"]),
                    can_receive_from=list(role["can_receive_from"]),
                    can_dispatch_tasks=bool(role["can_dispatch_tasks"]),
                    can_reassign_tasks=bool(role["can_reassign_tasks"]),
                )
                for role in effective["roles"]
            ],
        )
    )


def lifecycle_statuses(response: dict[str, Any]) -> list[str]:
    return [str(event["status"]) for event in response["events"]]


def websocket_trace(agent_id: str) -> dict[str, Any]:
    try:
        import websockets.sync.client
    except ImportError:
        return {"available": False, "reason": "websockets package not installed"}

    ws_url = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_url}/ws/tracing/agents/{urllib.parse.quote(agent_id)}"
    try:
        with websockets.sync.client.connect(url, open_timeout=5) as websocket:
            message = websocket.recv(timeout=5)
            return {"available": True, "url": url, "message": json.loads(message)}
    except Exception as exc:  # pragma: no cover - evidence should capture runtime failures.
        return {"available": False, "url": url, "reason": str(exc)}


def write_report(evidence: dict[str, Any]) -> None:
    checks = evidence.get("checks", {})
    gaps = evidence.get("gaps", [])
    lines = [
        "# AOP Smoke E2E Report",
        "",
        f"- Run ID: `{evidence['run_id']}`",
        f"- Base URL: `{BASE_URL}`",
        f"- Generated UTC: `{evidence['generated_at']}`",
        "",
        "## Result",
        "",
        f"- Overall: `{evidence['result']}`",
        f"- Health: `{checks.get('health')}`",
        f"- Ready: `{checks.get('ready')}`",
        f"- Metrics: `{checks.get('metrics')}`",
        f"- Topology ACL default-deny lateral block: `{checks.get('topology_lateral_block')}`",
        f"- Socket task lifecycle: `{checks.get('socket_lifecycle')}`",
        f"- Terminal task lifecycle: `{checks.get('terminal_lifecycle')}`",
        f"- Trace filters: `{checks.get('trace_filters')}`",
        f"- FinOps rollup: `{checks.get('finops_rollup')}`",
        f"- WebSocket trace: `{checks.get('websocket_trace')}`",
        "",
        "## Evidence File",
        "",
        f"- `{EVIDENCE_PATH.name}`",
        "",
        "## Gaps / Backlog",
        "",
    ]
    if gaps:
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("- None observed in this smoke.")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("e2e-%Y%m%dT%H%M%SZ")
    tenant_id = f"tenant-{run_id}"
    project_id = f"project-{run_id}"
    issue_id = f"issue-{run_id}"
    trace_id = f"trace-{run_id}"
    evidence: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "checks": {},
        "responses": {},
        "gaps": [],
        "result": "failed",
    }

    try:
        health = request_json("GET", "/health")
        ready = request_json("GET", "/health/ready")
        metrics = request_text("GET", "/metrics")
        evidence["responses"]["health"] = health
        evidence["responses"]["ready"] = ready
        evidence["responses"]["metrics_excerpt"] = metrics[:1000]
        assert_equal(health.get("status"), "ok", "health status")
        assert_true("coupling" in health, "health expõe coupling_status")
        assert_equal(ready["status"], "ready", "ready status")
        assert_true("aop_control_plane_up 1" in metrics, "metrics control plane up")
        evidence["checks"].update({"health": "passed", "ready": "passed", "metrics": "passed"})

        agents = {}
        for label, role, vendor in (
            ("Tech Lead", "orchestrator", "codex"),
            ("Worker A", "worker", "codex"),
            ("Worker B", "worker", "kiro"),
        ):
            created = request_json(
                "POST",
                "/agents",
                {
                    "tenant_id": tenant_id,
                    "label": f"{label} {run_id}",
                    "vendor": vendor,
                    "role": role,
                    "workspace_id": "workspace-main",
                    "pane_id": f"{run_id}-{label.lower().replace(' ', '-')}",
                    "stable_key": f"{run_id}/{label.lower().replace(' ', '-')}",
                },
            )
            agents[label] = created
        tl = agents["Tech Lead"]["agent_id"]
        worker_a = agents["Worker A"]["agent_id"]
        worker_b = agents["Worker B"]["agent_id"]
        evidence["responses"]["agents"] = agents

        topology = request_json(
            "POST",
            f"/squads/{run_id}/topology",
            {
                "nodes": [
                    {"id": tl, "role": "orchestrator"},
                    {"id": worker_a, "role": "worker"},
                    {"id": worker_b, "role": "worker"},
                ],
                "edges": [
                    {"source": tl, "target": worker_a},
                    {"source": worker_a, "target": tl},
                    {"source": tl, "target": worker_b},
                    {"source": worker_b, "target": tl},
                ],
            },
        )
        stored_topology = request_json("GET", f"/squads/{run_id}/topology")
        effective = topology["effective_topology"]
        acl = acl_from_effective(effective)
        lateral_allowed = acl.can_send(worker_a, worker_b)
        tl_to_worker = acl.can_send(tl, worker_a)
        worker_to_tl = acl.can_send(worker_a, tl)
        assert_equal(effective["default_policy"], "deny", "topology default policy")
        assert_true(tl_to_worker, "tech lead can send to worker")
        assert_true(worker_to_tl, "worker can send to tech lead")
        assert_true(not lateral_allowed, "worker lateral communication blocked")
        evidence["responses"]["topology"] = topology
        evidence["responses"]["stored_topology"] = stored_topology
        evidence["responses"]["topology_violation"] = {
            "from_agent": worker_a,
            "to_agent": worker_b,
            "blocked": not lateral_allowed,
            "reason": "AclEngine default_policy=deny and no worker_a -> worker_b edge",
        }
        evidence["checks"]["topology_lateral_block"] = "passed"

        socket_task = request_json(
            "POST",
            "/tasks",
            {
                "task_id": f"task-socket-{run_id}",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "issue_id": issue_id,
                "assignee_runtime": worker_a,
                "prompt": "E2E socket smoke task",
                "operation_mode": "socket",
                "seat_seconds": 5,
            },
        )
        terminal_task = request_json(
            "POST",
            "/tasks",
            {
                "task_id": f"task-terminal-{run_id}",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "issue_id": issue_id,
                "assignee_runtime": worker_b,
                "prompt": "E2E terminal smoke task",
                "operation_mode": "terminal",
                "seat_seconds": 5,
            },
        )
        assert_equal(lifecycle_statuses(socket_task), ["queued", "claimed", "running", "done"], "socket lifecycle")
        assert_equal(lifecycle_statuses(terminal_task)[-1], "done", "terminal final status")
        evidence["responses"]["tasks"] = {"socket": socket_task, "terminal": terminal_task}
        evidence["checks"]["socket_lifecycle"] = "passed"
        evidence["checks"]["terminal_lifecycle"] = "passed"

        trace_event = request_json(
            "POST",
            "/tracing/events",
            {
                "trace_id": trace_id,
                "layer": "l1_execution",
                "signal_type": "burn",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "issue_id": issue_id,
                "agent_id": worker_a,
                "runtime_id": worker_a,
                "message": "E2E trace burn sample",
                "token_burn": 42,
                "seat_seconds": 7,
            },
        )
        by_agent = request_json("GET", f"/tracing/agents/{urllib.parse.quote(worker_a)}")
        by_runtime = request_json("GET", f"/tracing/runtimes/{urllib.parse.quote(worker_a)}")
        assert_true(any(event["trace_id"] == trace_id for event in by_agent), "trace by agent")
        assert_true(any(event["trace_id"] == trace_id for event in by_runtime), "trace by runtime")
        ws_result = websocket_trace(worker_a)
        assert_true(ws_result.get("available"), "websocket trace available")
        evidence["responses"]["tracing"] = {
            "posted": trace_event,
            "by_agent": by_agent,
            "by_runtime": by_runtime,
            "websocket": ws_result,
        }
        evidence["checks"]["trace_filters"] = "passed"
        evidence["checks"]["websocket_trace"] = "passed"

        token_cost = request_json(
            "POST",
            "/finops/costs/token",
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "issue_id": issue_id,
                "agent_id": worker_a,
                "runtime_id": worker_a,
                "input_tokens": 100,
                "output_tokens": 50,
                "input_token_price_usd": "0.000001",
                "output_token_price_usd": "0.000002",
                "model": "e2e-model",
                "trace_id": trace_id,
            },
        )
        seat_cost = request_json(
            "POST",
            "/finops/costs/seat",
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "issue_id": issue_id,
                "agent_id": worker_b,
                "runtime_id": worker_b,
                "seat_id": "local-seat-codex",
                "vendor": "codex",
                "used_seconds": 60,
                "period_seconds": 3600,
                "period_cost_usd": "12.00",
                "trace_id": trace_id,
            },
        )
        rollup = request_json(
            "GET",
            f"/finops/projects/{urllib.parse.quote(tenant_id)}/{urllib.parse.quote(project_id)}/rollup",
        )
        assert_true(int(rollup["record_count"]) >= 2, "finops record count")
        assert_true(float(rollup["total_cost_usd"]) > 0, "finops total cost")
        evidence["responses"]["finops"] = {
            "token_cost": token_cost,
            "seat_cost": seat_cost,
            "rollup": rollup,
        }
        evidence["checks"]["finops_rollup"] = "passed"

        evidence["gaps"].append(
            "AOP has no public send_message/handoff endpoint yet; lateral block was proven by applying HerdMaster AclEngine to the effective ACL returned by /squads/{id}/topology."
        )
        evidence["gaps"].append(
            "HerdMaster :8080 returned 401 without bearer token in this environment, so socket-mode dispatch used the ADR-001 fallback path unless a tokenized HerdMaster client is added."
        )
        if "coupling" not in json.dumps(health):
            evidence["gaps"].append("GET /health does not expose coupling_status yet; AppState has it, but the route response omits it.")

        evidence["result"] = "passed"
        return 0
    except Exception as exc:
        evidence["error"] = str(exc)
        return 1
    finally:
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
        write_report(evidence)
        print(json.dumps({"result": evidence["result"], "run_id": run_id, "evidence": str(EVIDENCE_PATH), "report": str(REPORT_PATH), "checks": evidence["checks"], "error": evidence.get("error")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

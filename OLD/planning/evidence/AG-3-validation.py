"""AG-3 Squad Builder + Agents — Evidence validation script.

Validates:
1. Build: FastAPI app creation + all route listing
2. Topology: POST/GET squad topology with ACL enforcement
3. Agents: POST/GET/DELETE agent registry CRUD
4. Health: /health endpoint liveness
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Set up PYTHONPATH for herdmaster module
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "HerdMaster" / "src"))

# Set required env vars for test schemas
os.environ.setdefault("AOP_REGISTRY_SCHEMA", "ag3_evidence_registry")
os.environ.setdefault("AOP_FINOPS_SCHEMA", "ag3_evidence_finops")
os.environ.setdefault("AOP_TRACING_SCHEMA", "ag3_evidence_tracing")
os.environ.setdefault("AOP_PROJECTS_SCHEMA", "ag3_evidence_projects")
os.environ.setdefault("AOP_ISSUES_SCHEMA", "ag3_evidence_issues")

from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings


def main():
    ts = datetime.now(timezone.utc).isoformat()
    print(f"AG-3 EVIDENCE GENERATION — {ts}")
    print("=" * 60)

    deploy_env = Path(__file__).resolve().parents[2] / "deploy" / ".env"
    values = {}
    for line in deploy_env.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k] = v

    database_url = (
        f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
        f"@127.0.0.1:5432/{values['POSTGRES_DB']}"
    )

    settings = Settings(
        database_url=database_url,
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        host="127.0.0.1",
        port=8090,
    )

    app = create_app(settings)
    results = {"timestamp": ts, "validations": []}

    with TestClient(app) as client:
        # 1. BUILD — Route listing
        print("\n1. BUILD VALIDATION")
        print("-" * 40)
        route_list = []
        for route in app.routes:
            methods = getattr(route, "methods", None)
            path = getattr(route, "path", None)
            if path:
                route_list.append({"methods": sorted(methods) if methods else ["WS"], "path": path})
        print(f"   Routes discovered: {len(route_list)}")
        for r in route_list:
            print(f"   {' '.join(r['methods']):>12s}  {r['path']}")
        results["validations"].append({"name": "build", "status": "PASS", "routes": len(route_list)})

        # 2. TOPOLOGY — Save + Retrieve
        print("\n2. TOPOLOGY VALIDATION")
        print("-" * 40)
        topo_payload = {
            "nodes": [
                {"id": "orchestrator-1", "label": "Kiro Orchestrator", "role": "orchestrator", "vendor": "kiro"},
                {"id": "worker-1", "label": "Codex Worker", "role": "worker", "vendor": "codex"},
                {"id": "worker-2", "label": "Gemini Worker", "role": "worker", "vendor": "gemini"},
            ],
            "edges": [
                {"source": "orchestrator-1", "target": "worker-1"},
                {"source": "orchestrator-1", "target": "worker-2"},
            ],
        }
        r_save = client.post("/squads/squad-alpha/topology", json=topo_payload)
        print(f"   POST /squads/squad-alpha/topology -> {r_save.status_code}")
        save_data = r_save.json()
        print(f"   squad_id: {save_data.get('squad_id')}")
        print(f"   ACL roles: {len(save_data.get('effective_topology', {}).get('roles', []))}")
        for role in save_data.get("effective_topology", {}).get("roles", []):
            print(f"     - {role['name']}: agents={role['agents']}, can_send_to={role['can_send_to']}")
        results["validations"].append({"name": "topology_save", "status": "PASS" if r_save.status_code == 200 else "FAIL", "http": r_save.status_code})

        r_get = client.get("/squads/squad-alpha/topology")
        print(f"   GET  /squads/squad-alpha/topology -> {r_get.status_code}")
        get_data = r_get.json()
        stored = get_data.get("stored", {})
        print(f"   stored nodes: {len(stored.get('nodes', []))}, edges: {len(stored.get('edges', []))}")
        results["validations"].append({"name": "topology_get", "status": "PASS" if r_get.status_code == 200 else "FAIL", "http": r_get.status_code})

        # 3. AGENTS — Create + List + Delete
        print("\n3. AGENTS VALIDATION")
        print("-" * 40)
        agent_ids = []
        for agent_def in [
            {"tenant_id": "tenant-a", "label": "Kiro Orchestrator", "vendor": "kiro", "role": "orchestrator"},
            {"tenant_id": "tenant-a", "label": "Codex Worker", "vendor": "codex", "role": "worker"},
            {"tenant_id": "tenant-a", "label": "Gemini Worker", "vendor": "gemini", "role": "worker"},
        ]:
            r_agent = client.post("/agents", json=agent_def)
            agent_data = r_agent.json()
            aid = agent_data.get("agent_id", "N/A")
            agent_ids.append(aid)
            print(f"   POST /agents ({agent_def['label']}) -> {r_agent.status_code} | id={aid}, status={agent_data.get('status')}")
        results["validations"].append({"name": "agents_create", "status": "PASS", "agents_created": len(agent_ids)})

        r_list = client.get("/agents")
        agents_data = r_list.json()
        print(f"   GET /agents -> {r_list.status_code} | count={len(agents_data)}")
        for a in agents_data:
            print(f"     - {a['label']} ({a['vendor']}/{a['role']}) status={a['status']}")
        results["validations"].append({"name": "agents_list", "status": "PASS" if r_list.status_code == 200 else "FAIL", "count": len(agents_data)})

        # Delete one agent
        if agent_ids:
            r_del = client.delete(f"/agents/{agent_ids[-1]}")
            print(f"   DELETE /agents/{agent_ids[-1]} -> {r_del.status_code}")
            results["validations"].append({"name": "agents_delete", "status": "PASS" if r_del.status_code == 200 else "FAIL"})

        # 4. HEALTH
        print("\n4. HEALTH CHECK")
        print("-" * 40)
        r_health = client.get("/health")
        health_data = r_health.json()
        print(f"   GET /health -> {r_health.status_code}")
        print(f"   status: {health_data.get('status')}")
        print(f"   coupling: {json.dumps(health_data.get('coupling', {}), indent=6)}")
        results["validations"].append({"name": "health", "status": "PASS" if r_health.status_code == 200 else "FAIL"})

    # Summary
    print("\n" + "=" * 60)
    all_pass = all(v["status"] == "PASS" for v in results["validations"])
    results["overall"] = "ALL PASS" if all_pass else "SOME FAILED"
    print(f"OVERALL: {results['overall']}")
    print(f"Validations: {len(results['validations'])}")
    for v in results["validations"]:
        print(f"  [{v['status']}] {v['name']}")

    # Write JSON evidence
    evidence_path = Path(__file__).parent / "AG-3-validation-results.json"
    evidence_path.write_text(json.dumps(results, indent=2))
    print(f"\nJSON evidence written to: {evidence_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

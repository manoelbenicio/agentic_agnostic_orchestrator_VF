#!/usr/bin/env python3
"""
QA núcleo reproduzível — HerdMaster.

Bateria de QA da camada de núcleo (repos + fila + projeto) contra um DB SQLite
temporário. Saída em JSON auditável: cada caso traz id, descrição, esperado,
obtido e veredito. Usado pelo QA_EXECUTION_REPORT_v1.0.0.md.

Reproduzir:
    ./.venv/bin/python scripts/qa_core.py

Código de saída: 0 se todos PASS, 1 se houver qualquer FAIL.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from herdmaster.db import schema, repositories  # noqa: E402
from herdmaster.dispatch.queue import TaskQueue  # noqa: E402

EV: list[dict] = []


def case(cid: str, desc: str, expected, actual_fn) -> None:
    try:
        res = actual_fn()
        ok = res.get("ok") if isinstance(res, dict) else bool(res)
        val = res.get("val") if isinstance(res, dict) else res
        EV.append({"id": cid, "desc": desc, "expected": expected, "actual": val,
                   "verdict": "PASS" if ok else "FAIL"})
    except Exception as e:  # noqa: BLE001
        EV.append({"id": cid, "desc": desc, "expected": expected,
                   "actual": f"EXC:{type(e).__name__}:{e}", "verdict": "FAIL"})


def main() -> int:
    db = tempfile.mktemp(suffix=".db")
    conn = schema.connect(db)
    schema.init_db(conn)
    ar = repositories.AgentRepo(conn)
    tr = repositories.TaskRepo(conn)
    pr = repositories.ProjectRepo(conn)
    q = TaskQueue(tr, ar)

    case("DB-WAL", "journal_mode=WAL", "wal",
         lambda: {"ok": conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal",
                  "val": conn.execute("PRAGMA journal_mode").fetchone()[0]})
    case("DB-SCHEMA", "6 tabelas", 6,
         lambda: (lambda t: {"ok": len(t) == 6, "val": len(t)})(
             [r[0] for r in conn.execute(
                 "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]))
    case("DB-IDX", "8 índices idx_*", 8,
         lambda: (lambda i: {"ok": len(i) >= 8, "val": len(i)})(
             [r[0] for r in conn.execute(
                 "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")]))

    ar.upsert("A1", "Orq", "claude", "orchestrator", state="idle")
    ar.upsert("A2", "W1", "codex", "worker", state="idle")
    case("AG-01", "criar agente", "get(A1)!=None",
         lambda: {"ok": ar.get("A1") is not None, "val": ar.get("A1") is not None})
    case("AG-02", "listar agentes", "len==2",
         lambda: {"ok": len(ar.list()) == 2, "val": len(ar.list())})
    case("AG-04", "update_state A2->working", "working",
         lambda: (ar.update_state("A2", "working"),
                  {"ok": ar.get("A2")["state"] == "working", "val": ar.get("A2")["state"]})[1])
    case("AG-05", "update_health A2->suspect", "suspect",
         lambda: (ar.update_health("A2", "suspect"),
                  {"ok": ar.get("A2")["health"] == "suspect", "val": ar.get("A2")["health"]})[1])
    case("AG-06", "DELETAR agente", "método delete existe",
         lambda: {"ok": any(hasattr(ar, m) for m in ("delete", "remove")),
                  "val": [m for m in ("delete", "remove") if hasattr(ar, m)] or "NENHUM"})

    t1 = q.enqueue("crit", "p", priority="critical", assigned_to="A2")
    t2 = q.enqueue("low", "p", priority="low", assigned_to="A2")
    q.enqueue("dep", "p", priority="high", assigned_to="A2", depends_on=[t1])
    case("TK-01", "criar tarefa (queued)", "queued",
         lambda: {"ok": tr.get(t1)["state"] == "queued", "val": tr.get(t1)["state"]})
    case("TK-06", "prioridade critical>low", "[crit,low]",
         lambda: (lambda r: {"ok": r[0] == "crit", "val": r})([t["title"] for t in q.ready_tasks()]))
    case("TK-07", "dep oculta dependente", "dep ausente",
         lambda: (lambda r: {"ok": "dep" not in r, "val": r})([t["title"] for t in q.ready_tasks()]))
    case("TK-08", "claim CAS pega critical", "crit",
         lambda: (lambda c: {"ok": bool(c) and c["title"] == "crit", "val": c["title"] if c else None})(
             asyncio.run(q.claim_next("A2"))))
    case("TK-05", "cancelar tarefa", "cancelled",
         lambda: (q.cancel(t2), {"ok": tr.get(t2)["state"] == "cancelled", "val": tr.get(t2)["state"]})[1])

    pid = pr.create("Proj", "escopo")
    case("PJ-01", "criar projeto", "get!=None",
         lambda: {"ok": pr.get(pid) is not None, "val": pr.get(pid) is not None})
    case("PJ-05a", "update_state approved", "approved",
         lambda: (pr.update_state(pid, "approved"),
                  {"ok": pr.get(pid)["state"] == "approved", "val": pr.get(pid)["state"]})[1])

    print(json.dumps(EV, ensure_ascii=False, indent=1))
    fails = [e["id"] for e in EV if e["verdict"] == "FAIL"]
    print(f"\nRESUMO: {len(EV) - len(fails)} PASS / {len(fails)} FAIL -> {fails or 'verde'}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())

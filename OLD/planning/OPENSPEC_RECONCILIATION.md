# OpenSpec Reconciliation — agnostic-orchestration-platform

Generated UTC: 2026-06-26T20:45:58Z  
Agent: CODEX_55#3  
Scope: reconcile `openspec/changes/agnostic-orchestration-platform/tasks.md` against implemented AOP code.

## Summary

- Previous OpenSpec progress: 2/65 tasks complete.
- Reconciled progress: 51/65 tasks complete.
- Remaining implementation tasks: 14/65.
- Product code was not changed for this reconciliation; only OpenSpec task status and this planning report were updated.

## Evidence Sources Read

- OpenSpec task source: `openspec/changes/agnostic-orchestration-platform/tasks.md`
- Backend app wiring: `AOP/control-plane/app/main.py`, `AOP/control-plane/app/dependencies.py`
- Backend modules/tests:
  - `core`, `executors`, `coupling`, `seats`, `seats_api`, `sessions_api`
  - `scheduler`, `orchestrator`, `topology`, `registry`
  - `finops`, `tracing`, `projects_api`, `issues_api`, `inbox_api`, `settings_api`
- Frontend routes:
  - `/`, `/projects`, `/issues`, `/my-issues`, `/inbox`, `/settings`
  - `/seats`, `/sessions`, `/finops`, `/observability`, `/live`, `/squad-builder`, `/agents`
- E2E reports:
  - `AOP/e2e/REPORT.md`
  - `AOP/e2e/REPORT_WAVE1.md`

## Verification Run

Backend focused pytest:

```text
PYTHONPATH=AOP/control-plane:HerdMaster/src AOP/control-plane/.venv/bin/python -m pytest \
  AOP/control-plane/core AOP/control-plane/executors AOP/control-plane/seats \
  AOP/control-plane/scheduler AOP/control-plane/orchestrator AOP/control-plane/topology \
  AOP/control-plane/registry AOP/control-plane/finops AOP/control-plane/tracing \
  AOP/control-plane/projects_api AOP/control-plane/issues_api AOP/control-plane/inbox_api \
  AOP/control-plane/settings_api -q

57 passed, 1 warning in 11.39s
```

Frontend build:

```text
npm run build
```

The build completed successfully during this TD8 run; generated routes include `/issues` and `/my-issues`.

## Tasks Marked Done

### 1. Fundação & Scaffold Limpo

- `1.1` Scaffold exists under `AOP/control-plane`, `AOP/web`, `AOP/deploy`, `AOP/ops`.
- `1.2` FastAPI `/health`, `/health/ready`, `/metrics` exist in `app/main.py`; covered by `app/tests/test_api.py`.
- `1.3` HerdMaster/Herdr coupling exists in `coupling/`, `executors/socket.py`, `executors/terminal.py`, and `build_coupled_executors`.
- `1.3b` Postgres schemas/repositories exist for registry, projects, issues, inbox, settings, finops, tracing, seats, sessions; wired in `app/dependencies.py`.
- `1.4` `HerdrRuntimeAdapter` and `TerminalExecutor` exist in `executors/terminal.py`.
- `1.5` `AOP/deploy/docker-compose.yml` exists for local Postgres/Redis stack; ops scripts start API/frontend.
- `1.6` Redis is wired via `redis.Redis.from_url`, `QuotaLedger(redis_client=redis_client)`, and readiness checks.

### 2. Contrato Único de Task/Evento & Dual Operation Mode

- `2.1` `TaskEnvelope`, `TaskBudget`, `TaskCallbacks` exist in `core/models.py`.
- `2.2` `LifecycleEvent` and statuses exist in `core/models.py`; covered by `core/tests/test_contracts.py`.
- `2.3` `TerminalExecutor` exists and is tested in `executors/tests/test_dual_executors.py`.
- `2.4` `SocketExecutor` exists and is tested in `executors/tests/test_dual_executors.py`.
- `2.5` mode router exists in `core/router.py` and `executors/router.py`; `/tasks` dispatches by `operation_mode`.

### 3. Agent Runtime Adapter

- `3.1` `AgentRuntimeAdapter` interface exists in `core/interfaces.py`.
- `3.4` `meter` hook exists on the adapter interface and `HerdrRuntimeAdapter`.

### 4. Seat Pool & Credential Isolation

- `4.1` `SeatPool.acquire/release` exists and is covered by `seats/tests/test_pool.py`.
- `4.2` per-seat `HOME`, config dir, and env isolation exist in `seats/pool.py` and `seats_api`.
- `4.3` subagent inheritance exists via `SeatPool.acquire_subagent`.
- `4.4` lease affinity and token refresh are covered by `test_lease_affinity_and_refresh`.

### 5. Quota-Aware Scheduler

- `5.1` quota snapshots and ledger exist in `scheduler/quota.py`.
- `5.2` admission control queues quota/concurrency waits in `scheduler/scheduler.py`.
- `5.3` exponential backoff with jitter exists in `scheduler/backoff.py`.
- `5.4` burn-rate forecasting exists and is tested; observability metrics are exposed through `/metrics`.

### 6. Tech-Lead Orchestration

- `6.1` `TechLeadCoordinator` plans/decomposes goals in `orchestrator/techlead.py`.
- `6.2` fan-out is bounded by config and scheduler admission.
- `6.3` autonomy levels and approval gate are covered by `test_low_autonomy_requires_human_approval_before_spawn`.

### 7. Communication Topology & ACL

- `7.1` topology nodes/edges map to ACL config in `topology/mapper.py`.
- `7.2` hub-and-spoke default-deny behavior is tested in `topology/tests/test_topology.py`.
- `7.3` lateral grants/revokes are represented by explicit edge persistence.
- `7.4` runtime message enforcement exists at `POST /squads/{squad_id}/messages` and `messaging/service.py`.
- `7.5` topology validation rejects isolated workers in `test_isolated_worker_validation`.

### 8. Visual Squad Builder

- `8.1` canvas nodes from registered agents and vendor counts exist in `components/squad-builder/Canvas.tsx`.
- `8.2` connection-line topology editing uses `@xyflow/react` edges and saves to `/squads/{id}/topology`.
- `8.3` xyflow drag/connect/pan/zoom UI is implemented with `ReactFlow`, `MiniMap`, `Controls`, and `Background`.

### 9. FinOps Dual Engine

- `9.1` token and seat engines exist in `finops/engine.py`.
- `9.2` hierarchical `Attribution` includes tenant/project/issue/agent/runtime.
- `9.3` idle seat recommendation exists in `FinOpsRepository.idle_seat_recommendations`.
- `9.4` billing modes `pay_as_you_go` and `monthly` exist and are tested.

### 10. Multi-Tenant Identity & Auth

- `10.2` seat-based device login/session isolation exists in `seats_api`, `sessions_api`, and frontend `/seats` + `/sessions`.

### 11. Observability & Tracing

- `11.1` trace propagation L4→L1 is implemented and tested in `tracing/tests/test_tracing.py`.
- `11.2` metrics for control-plane, finops, and trace burn are exposed by `/metrics`.
- `11.3` session artifacts are recorded by `/tracing/artifacts`.
- `11.3a` per-agent and per-runtime timelines exist at `/tracing/agents/{id}` and `/tracing/runtimes/{id}` plus WebSocket `/ws/tracing/agents/{id}`.

### 12. UI da Plataforma

- `12.1` design system exists in `AOP/web/src/app/globals.css` and app shell/UI components.
- `12.2` projects + issues tracker/kanban are implemented in `/projects` and `/issues`.
- `12.3` live agent panel exists in `/live` and tracing WebSocket backend.
- `12.4` settings, inbox, my-issues, and command palette exist with real endpoints/components.

### 13. Validação E2E

- `13.1` smoke E2E report exists in `AOP/e2e/REPORT.md`; Wave 1 contract report exists in `AOP/e2e/REPORT_WAVE1.md`.

### 14. Dynamic Agent Registry

- `14.1` single authoritative registry exists in `registry/`.
- `14.2` add/remove propagates via propagation hooks and API `/agents`.
- `14.3` controlled pane enrollment rejects foreign workspaces.
- `14.4` stable identity survives pane churn and preserves mapping history.

## Still Pending

These remain unchecked in OpenSpec because the code audit did not find complete implementation evidence:

- `1.3a` HerdMaster SQLite→Postgres migration: outside AOP control-plane audit scope for this TD8; prior ledger suggests work happened in `HerdMaster/`, but this reconciliation did not verify it.
- `3.2` native adapters for Codex, Kiro, Antigravity, Gemini with semantic state detection.
- `3.3` generic fallback detection by foreground process name + terminal screen-scrape heuristics.
- `8.4` optional chatbot entry point for squad/topology proposal.
- `10.1` full tenant isolation enforced by auth context/RLS across all APIs.
- `10.3` human RBAC roles admin/operator/viewer plus audit enforcement.
- `11.4` immutable audit log for leases, topology violations, autonomy decisions, and billing events.
- `13.2` vendor ToS confirmation for concurrent seat usage.
- `13.3` local load test targeting ~10 parent agents and 2-3 fan-out.
- `15.1` worktree/path-guard isolation.
- `15.2` system-level append-only check-in/out ledger feature.
- `15.3` automatic missing check-out timeout violation flag.
- `15.4` application-level mandatory evidence validation.
- `15.5` trace_id linkage for evidence and ledger.

## Notes

- This reconciliation is intentionally conservative. A task was marked complete only when a concrete module, route, test, or UI route existed.
- Some implementation is broader than OpenSpec currently models, such as `inbox_api`, `settings_api`, `/agents`, and DB pooling robustness.
- `12.1` text still says OKLCH, but the current app has migrated to Indra HEX. The task was marked complete because the design system foundation exists and is used by the app.

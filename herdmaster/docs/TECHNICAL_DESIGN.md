# HerdMaster Technical Design

This document describes the implemented HerdMaster control-plane core in this repository. It is source-verified against `src/herdmaster/{config,db,bus,herdr,dispatch,watchdog}/` and intentionally avoids documenting components that are not present in source yet.

Related diagrams generated separately and referenced by path:

- `docs/architecture_macro.html`
- `docs/architecture_micro.html`
- `docs/architecture_deep.html`

## Implemented Components

| Component | Source | Responsibility |
| --- | --- | --- |
| Configuration | `src/herdmaster/config.py` | Load TOML config, apply defaults, validate runtime knobs, watch config mtime, initialize logging. |
| SQLite data layer | `src/herdmaster/db/schema.py`, `src/herdmaster/db/repositories.py` | Create schema, open WAL-mode connections, expose repositories for agents, tasks, messages, projects, and health events. |
| Message schema | `src/herdmaster/bus/messages.py` | Define validated JSON-RPC 2.0 `Message` envelopes and message type enum. |
| Message bus server | `src/herdmaster/bus/server.py` | Async Unix-socket pub/sub with persistence, TTL expiry, groups, broadcast, and file fallback. |
| Herdr adapter | `src/herdmaster/herdr/adapter.py`, `src/herdmaster/herdr/parser.py` | Single async boundary around Herdr CLI commands and tolerant JSON parsers. |
| Task queue | `src/herdmaster/dispatch/queue.py` | Durable task lifecycle wrapper over `TaskRepo`, priority/FIFO ready ordering, CAS claiming, retry/reassignment. |
| Dispatch injector | `src/herdmaster/dispatch/injector.py` | Wait for idle agents, inject prompts into Herdr panes, chunk long input, use prompt-file fallback. |
| Watchdog | `src/herdmaster/watchdog/engine.py`, `src/herdmaster/watchdog/recovery.py` | Tri-layer health monitoring, health FSM transitions, recovery, and escalation messages. |

The database schema also contains project-mode tables and `ProjectRepo`, but planner/squad/API/TUI modules are not present in this source snapshot.

> **Last updated:** 2026-06-25T16:17Z — Allowlist guard, pipx editable install, observability stack (Prometheus+Alertmanager+Webhook) validados em produção. Ver também:
> - [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) — registro canônico de 7 agentes com roles, panes e mecanismo allowlist
> - [`COMMUNICATION_PROTOCOL.md`](COMMUNICATION_PROTOCOL.md) — ACL matrix e especificação do bus
> - [`OPS_RUNBOOK.md`](OPS_RUNBOOK.md) — comandos operacionais, stack de observabilidade e troubleshooting


## Runtime Topology

HerdMaster is designed as a local asyncio control plane layered on top of Herdr. The implemented runtime can be hosted on a single event loop with these long-running tasks:

| Task | Owner | Notes |
| --- | --- | --- |
| Bus socket server | `MessageBusServer.start()` | Creates an asyncio Unix server and a TTL sweep task. Each connected client gets a pump task for queued outbound messages. |
| Watchdog engine | `WatchdogEngine.start()` / `run()` | Starts a primary listener task when the adapter exposes a compatible state-change async iterator, plus a periodic polling loop. |
| Dispatch loop | External caller using `TaskQueue.claim_next()` and `DispatchInjector.dispatch()` | The loop itself is not implemented as a daemon in this snapshot; the queue and injector are ready to be composed by a runner. |
| Config watcher | `ConfigWatcher.watch()` | Optional mtime polling task that calls an injected callback after successful reload and validation. |

All blocking Herdr operations cross the `HerdrAdapter`, which uses `asyncio.create_subprocess_exec` with argument lists. No other component should invoke Herdr directly.

## Data Model

`connect()` enables SQLite WAL, foreign keys, a 5 second busy timeout, and `sqlite3.Row` mapping. `init_db()` creates these tables and indexes:

| Table | Purpose | Main writers |
| --- | --- | --- |
| `agents` | Agent registry, Herdr pane/workspace, current state, current health, heartbeat, output hash, metrics. | `AgentRepo`, watchdog, dispatch setup. |
| `tasks` | Queue and lifecycle state for standalone or project tasks. | `TaskRepo`, `TaskQueue`, `DispatchInjector`. |
| `messages` | Persisted bus audit log with delivery and acknowledgement flags. | `MessageRepo`, `MessageBusServer`. |
| `health_events` | Audit trail for health transitions. | `AgentRepo.update_health()` called by watchdog/recovery. |
| `projects` | Project mode metadata and progress counters. | `ProjectRepo`; no planner module is present yet. |
| `project_history` | Historical records for ETA learning. | `ProjectRepo`. |

Important indexes: `idx_tasks_state`, `idx_tasks_assigned`, `idx_tasks_priority`, `idx_tasks_project`, `idx_messages_to`, `idx_health_agent`, `idx_projects_state`, and `idx_project_history_complexity`.

Repository methods commit after each write. Callers share injected repository instances rather than opening hidden connections in most components. The bus server can lazily create a `MessageRepo` against a sibling `herdmaster.db` when one is not injected.

## Message Bus Contract

### Message Envelope

`Message` is the wire and in-process schema. It serializes as newline-delimited JSON-RPC 2.0:

```json
{
  "jsonrpc": "2.0",
  "method": "alert",
  "params": {
    "type": "alert",
    "from": "watchdog",
    "to": "broadcast",
    "correlation_id": null,
    "timestamp": "2026-06-21T00:00:00Z",
    "ttl_seconds": 300,
    "payload": {}
  },
  "id": "1780000000000-uuid"
}
```

Supported message types are `task_assign`, `task_update`, `heartbeat`, `chat`, `alert`, and `state_change`. Addressing supports:

- `to = "broadcast"` for every registered subscriber.
- `to = "group:<name>"` for programmatic group multicast.
- Any other `to` value for unicast to one registered agent ID.

### Socket Protocol

Clients register by sending a JSON-RPC `register` frame with `params.agent_id`. Normal messages are then parsed with `Message.from_json()`, persisted through `MessageRepo.insert()`, and routed to subscriber queues.

`MessageBusServer.send(msg)` is the direct in-process producer API. It persists and routes the same `Message` object without requiring a socket client.

### Delivery, TTL, and Backpressure

Per-agent queues are bounded by `max_queue_size` and drop the oldest message when full. Delivered messages are marked with `MessageRepo.mark_delivered()` after successful socket write. The TTL sweep task periodically calls `MessageRepo.expire()` to delete expired undelivered rows.

If Unix socket startup fails, `MessageBusServer` sets `_using_fallback` and routes messages to `FileFallbackBus`, which appends JSON lines to `<socket_path>.fallback` and truncates the file when it exceeds the configured size bound.

## Herdr Adapter Contract

`HerdrAdapter` is the only implemented Herdr I/O boundary. Public methods:

| Method | Herdr command | Return |
| --- | --- | --- |
| `agent_list()` | `herdr agent list --json` | `list[HerdrAgent]` |
| `pane_read(pane_id)` | `herdr pane read <pane_id>` | Terminal output string |
| `pane_send(pane_id, text, confirm=True)` | `herdr pane send <pane_id> <text>` | `None`; rejects `confirm=False` |
| `agent_wait(agent_id, state="idle", timeout=60)` | `herdr agent wait <id> --state <state> --timeout <n>` | `True` on success |
| `pane_list()` | `herdr pane list --json` | `list[HerdrPane]` |
| `workspace_list()` | `herdr workspace list --json` | Parsed JSON object |
| `spawn_agent(pane_id, command)` | `herdr pane run <pane_id> <command>` | `None` |

Failures, timeouts, invalid JSON, and non-zero Herdr exits become `HerdrError`.

The parsers accept either top-level lists or objects with `agents`/`panes`, `items`, or `data`. Unknown state strings normalize to `unknown`. `output_hash(text)` returns a SHA-256 hash used by the watchdog.

## Task Queue Contract

`TaskQueue` wraps an injected `TaskRepo` and optional `AgentRepo`.

Lifecycle states:

```text
queued -> assigned -> dispatched -> in_progress -> done
                                          |-> failed
                                          |-> timeout
queued/assigned/dispatched/in_progress -> cancelled
```

Key interfaces:

- `enqueue(...) -> task_id`: creates a queued task with priority, dependencies, optional assignee, retry limits, and timeout.
- `ready_tasks()`: returns queued tasks whose dependencies are all `done`, sorted by priority, created time, then ID.
- `claim_next(agent_id)`: serializes claims with an asyncio lock and uses `TaskRepo.claim(task_id, agent_id, expected_version)` as the database CAS guard.
- `mark_dispatched()`, `mark_in_progress()`, `mark_done()`, `mark_failed()`, `mark_timeout()`, `cancel()`: enforce local state transition rules and raise `TaskStateError` for invalid transitions.
- `reassign(task_id)`: returns failed or timed-out tasks to `queued` until retry count reaches `max_retries`, then returns an escalation result.
- Template methods are in-memory only; durable template storage is not implemented.

## Dispatch Injector Contract

`DispatchInjector.dispatch(task)` expects an already assigned task. It reloads the task from the repository and requires state `assigned`.

Dispatch flow:

1. Resolve `assigned_to` and prompt from the task.
2. Resolve pane ID from `agents.herdr_pane`, falling back to `adapter.agent_list()`.
3. Wait for Herdr idle with `adapter.agent_wait()`.
4. Send prompt through `_send_prompt()`.
5. Mark task `dispatched` and then `in_progress`.

Prompt delivery strategy:

- Prompts at or below `file_fallback_threshold_chars` are split into `max_chunk_chars` chunks and sent through `adapter.pane_send()`, followed by newline.
- If chunked send fails, the injector writes a prompt file under `fallback_dir`, clears current input with Ctrl-U, and sends an instruction pointing the agent at that file.
- Prompts over the threshold use the prompt-file path immediately.

Retry behavior:

- `AgentNotIdle` requeues the task once for later dispatch unless task retries are exhausted.
- Herdr errors retry with exponential backoff up to `retry_attempts`; final failure marks the task failed from its current state.

## Watchdog Contract

`WatchdogEngine` monitors agents using three layers:

| Layer | Implementation |
| --- | --- |
| Primary | Optional adapter async iterator named `subscribe_state_changes`, `state_changes`, `watch_state_changes`, or `watch_agents`. If missing or failing, polling continues. |
| Secondary | `adapter.agent_list()` in `poll_once()` / run loop, updating agent state and pane ID. |
| Tertiary | `adapter.pane_read()` and `output_hash()` comparison on `tertiary_hash_interval_s` or first observation. |

Per-agent health values are `healthy`, `suspect`, `unhealthy`, and `recovering`. Active Herdr states are `working`, `blocked`, and `unknown`; resting states are `idle` and `done`.

### Allowlist Guard (implementado 2026-06-25)

When `watchdog.agent_allowlist` is non-empty in `config.toml`, **both** `_sync_agent()` and
`_sync_primary_agent()` silently drop any Herdr pane whose ID is not in the set — before touching
the DB, the dispatcher, or the health monitor:

```python
# engine.py — applied identically in both _sync_agent and _sync_primary_agent
if self.config.agent_allowlist and agent.id not in self.config.agent_allowlist:
    log.debug("allowlist: ignoring unregistered Herdr pane %r", agent.id)
    return
```

`WatchdogConfig.agent_allowlist` is a `frozenset[str]` populated from `config.toml`:

```toml
[watchdog]
agent_allowlist = ["cli", "w6:p1", "w6:p2", "w6:p5", "w6:p6", "w6:p7", "w6:p8"]
```

When the list is **empty** (default), all agents pass through — fully backwards-compatible.
This is the primary defence against phantom auto-registration from Herdr workspace syncs.

State evaluation:

- Activity or resting state records heartbeat and returns non-healthy agents to `healthy`.
- No progress past `soft_timeout_s` moves `healthy -> suspect`.
- No progress past `hard_timeout_s` moves to `unhealthy`, then starts recovery and marks `recovering`.
- Every health transition calls `AgentRepo.update_health()`, which updates `agents.health` and writes `health_events`.
- Every transition emits a `state_change` `Message` through the injected bus publisher when provided.

`RecoveryManager` performs recovery without importing dispatch internals:

1. Resolve pane ID and spawn command from arguments, repository fields, or an injected resolver.
2. Kill the hung process through adapter kill methods if available, otherwise send Ctrl-C through `pane_send()`.
3. Respawn with `adapter.spawn_agent()`.
4. Wait for idle with `adapter.agent_wait()`.
5. Replay the last task through an injected public replayer/callable.
6. Reset failure count on success.
7. Emit an `alert` `Message` after `max_retries` consecutive failures.

When the engine creates a manager internally, it passes `manage_health_events=False` so the engine remains the owner of FSM transition rows. A standalone `RecoveryManager` can manage health rows itself.

## Configuration Contract

`load_config(path=None)` reads TOML or returns defaults when the default config file is absent. `validate_config()` enforces:

- `watchdog.soft_timeout_s < watchdog.hard_timeout_s`
- positive watchdog poll and tertiary intervals
- `watchdog.max_retries >= 0`
- `bus.message_ttl_s > 0`
- `acl.default_policy` is `allow` or `deny`
- unique ACL role names and string lists
- API port in `1..65535`
- logging level in `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

`ConfigWatcher` polls mtime and invokes a callback only after successful reload and validation. Bad reloads are logged and the old config remains active.

## Error Handling Strategy

| Boundary | Error type / handling |
| --- | --- |
| Config load | Bad TOML or invalid values raise `ConfigError`; watcher logs and keeps prior config. |
| Herdr CLI | `OSError`, timeout, non-zero exit, and invalid parser output become `HerdrError`. |
| Bus parsing | Invalid JSON or invalid `Message` frames are discarded and logged; connection remains alive. |
| Bus socket bind | Falls back to file-backed message append instead of crashing. |
| Bus persistence | Message persistence failures are logged; routing still proceeds. |
| Queue transitions | Invalid lifecycle moves raise `TaskStateError`; missing rows raise `KeyError`. |
| Dispatch | Herdr idle failures requeue or fail; Herdr send failures retry then fail the task. |
| Watchdog primary source | Missing or failing primary stream marks flags and leaves secondary polling active. |
| Recovery | Recovery exceptions increment consecutive failure count; retry exhaustion emits `alert`. |

## Data Flows

### Task Dispatch

1. Caller enqueues a task through `TaskQueue.enqueue()`.
2. Dispatch loop calls `TaskQueue.claim_next(agent_id)`.
3. `TaskRepo.claim()` changes `queued -> assigned` only if version matches.
4. `DispatchInjector.dispatch()` waits for idle Herdr agent, sends prompt, and marks task `dispatched -> in_progress`.
5. Later caller marks task `done`, `failed`, or `timeout` through queue methods.

### Message Delivery

1. Producer builds a `Message` or calls `new_message()`.
2. Producer sends through socket or `MessageBusServer.send()`.
3. Server persists to SQLite and routes to unicast, broadcast, group, or fallback file.
4. Subscriber pump writes JSON line to socket and marks the message delivered.
5. TTL sweep removes expired undelivered rows.

### Health Monitoring and Recovery

1. Watchdog observes agent state/output from primary events, secondary polling, or tertiary hash checks.
2. Progress updates heartbeat and output hash.
3. Timeout evaluation transitions health and writes `health_events`.
4. Recovery interrupts or kills the current process through Herdr, respawns, waits for idle, and replays last task through an injected replayer.
5. Failed recoveries eventually emit `alert` messages for human action.

Those items are suitable for the deployment work breakdown in `../PARALLEL_TASKS.md`.

## ACL Engine — Implementado (verificado 2026-06-25)

O `AclEngine` em `src/herdmaster/acl/engine.py` **está implementado e ativo** em produção. A nota anterior estava incorreta.

### Política Padrão

```toml
[acl]
default_policy = "deny"  # Tudo bloqueado exceto explicitamente autorizado
```

### Roles em Produção

| Role | Agentes | can_dispatch | can_reassign | can_send_to |
|------|---------|-------------|-------------|-------------|
| `orchestrator` | `cli`, `w6:p7` | ✅ | ✅ | `"*"` (qualquer) |
| `worker` | `w6:p1`, `w6:p2`, `w6:p5`, `w6:p6`, `w6:p8` | ❌ | ❌ | `"orchestrator"` |
| `peer_reviewer` | — | ❌ | ❌ | `"orchestrator"`, `"peer_reviewer"` |
| `observer` | — | ❌ | ❌ | nenhum |

### Regra crítica — Squad Filtering

`src/herdmaster/project/squad.py:33` filtra orchestrators **antes** de qualquer atribuição de task:

```python
healthy = [
    agent for agent in agents
    if str(agent.get("health") or "healthy") == "healthy"
    and str(agent.get("role") or "") != "orchestrator"  # ← orchestrators NUNCA recebem tasks
]
```

### Por que o CLI Operator não tem pane Herdr?

O `cli` é um **seed agent** de sistema com `role=orchestrator`. O campo `herdr_pane TEXT` é
nullable by design (`schema.py:17`). Ele nunca recebe tasks — portanto nunca precisa de pane.

O erro `"agent 'cli' has no resolvable Herdr pane"` (`injector.py:157`) ocorreu quando o
LLM planner atribuiu tasks incorretamente ao `cli`. **Correção aplicada:** `role=orchestrator`
em `cli`, `Kiro_Opus-48` e `w8:p6` em `2026-06-25T15:22:42Z`.

## Agent Registry — Produção (2026-06-25)

Ver [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) para o registry canônico completo e mecanismo de allowlist.

Resumo — **7 agentes** (fonte: `herdmaster.db` verificado `2026-06-25T16:17Z`):
- **2 orchestrators:** `cli` (CLI Operator, sem pane), `w6:p7` (Kiro_Opus-48)
- **5 workers:** `w6:p1` AGY_Opus-46 · `w6:p2` AGY_Gemini_PRO-31 · `w6:p5` Codex_#1 · `w6:p6` Codex_#2 · `w6:p8` AGY_Flash35-High-Thinking

**Allowlist guard ativo** — qualquer pane Herdr fora desta lista é ignorado na origem pelo watchdog.


## OPS Commands (desde 2026-06-25)

Ver [`OPS_RUNBOOK.md`](OPS_RUNBOOK.md) para o runbook completo.

Aliases instalados em `~/.bashrc`:
```bash
hm-status   # estado completo (sem alterar)
hm-start    # inicia Control Plane
hm-stop     # para Control Plane (preserva tudo)
hm-restart  # restart SEM apagar dados
hm-reset    # reset-soft (limpa resíduos, preserva DB)
hm-agents   # /chat new em todos os agentes
hm-flush    # FLUSH TOTAL (apaga DB — pede CONFIRMO)
```

## Observability Stack (implementado 2026-06-25)

HerdMaster exporta métricas Prometheus via `/metrics` no servidor HTTP (`--http`, porta 8080).

### Métricas exportadas

| Métrica | Tipo | Descrição |
|---------|------|----------|
| `herdmaster_agents_total` | Gauge | Total de agentes no DB |
| `herdmaster_unlisted_agents_total` | Gauge | Agentes no DB fora do allowlist (esperado: 0) |
| `herdmaster_whitelist_compliant` | Gauge | 1 se todos os agentes são canônicos, 0 se há phantoms |
| `herdmaster_tasks_total` | Gauge | Tasks por estado |

### Stack

| Componente | Porta | Função |
|------------|-------|--------|
| Prometheus | 9090 | Scrape de métricas a cada 5s, 7 alert rules |
| Alertmanager | 9093 | Roteamento de alertas → webhook |
| Webhook Remediation | 9099 | Executa purge via `DELETE /agents/{id}` na HTTP API |
| Grafana | 3000 | Dashboard "Registry Integrity" com 6 painéis |

### Alert Rules (7 regras em 3 grupos)

| Grupo | Regra | Condição | Severidade |
|-------|-------|----------|----------|
| registry | `UnlistedAgentsDetected` | `unlisted > 0` por 10s | warning |
| registry | `WhitelistComplianceViolation` | `compliant == 0` por 10s | critical |
| registry | `AgentCountAnomaly` | count fora de 7 | warning |
| health | `AgentUnhealthy` | health == unhealthy | warning |
| health | `MultipleAgentsUnhealthy` | > 1 agente unhealthy | critical |
| ops | `HerdMasterDown` | scrape falha | critical |
| ops | `HighTaskFailureRate` | > 3 failed tasks | warning |

### Loop de Remediação E2E (validado 2026-06-25T16:15:27Z)

```
Ghost injetado → Prometheus detecta (10s) → Alert FIRING (25s)
  → Alertmanager → POST /webhook/remediate
  → webhook: DELETE http://127.0.0.1:8080/agents/{ghost_id}
  → HerdMaster apaga do DB (single DB owner)
  → Prometheus re-scrape → unlisted=0, compliant=1
  → Alertmanager RESOLVED
```

Tempo total de remediação observado: **~45s**.

**Arquitectura single-writer:** o webhook NÃO acessa SQLite diretamente — usa a HTTP API.
Isso elimina 100% do problema de `database is locked`.

## Pipx Editable Install (desde 2026-06-25)

O HerdMaster está instalado em modo editável:

```bash
pipx install --editable /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster
```

O arquivo `.pth` em `~/.local/share/pipx/venvs/herdmaster/lib/.../site-packages/__editable__.herdmaster-1.0.0.pth`
aponta para `src/` do repositório. **Toda modificação no source é imediatamente activa** sem necessidade de
reinstalar ou copiar arquivos manualmente.

## Gaps Atualizados (2026-06-25T16:17Z)

| Item | Status |
|------|--------|
| ACL enforcement engine | ✅ **IMPLEMENTADO** — `acl/engine.py` ativo |
| Control API server | ✅ **IMPLEMENTADO** — `api/server.py`, porta 8080 |
| TUI/dashboard | ✅ **IMPLEMENTADO** — `tui/dashboard.py` |
| Project planner | ✅ **IMPLEMENTADO** — `project/planner.py`, `project/squad.py` |
| ETA model | ✅ **IMPLEMENTADO** — `project/eta.py` |
| Top-level daemon | ✅ **RUNNING** — `herdmaster start --http` (editable install) |
| Allowlist guard | ✅ **IMPLEMENTADO** — `watchdog/engine.py` + `config.toml` |
| Observability stack | ✅ **RUNNING** — Prometheus+Alertmanager+Webhook+Grafana em Docker |
| E2E remediation loop | ✅ **VALIDADO** — ghost→alert→purge em ~45s (2026-06-25T16:15Z) |
| End-to-end tests | ⏳ pendente — framework a definir |
| Chaos/load harnesses | ⏳ pendente |

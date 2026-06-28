# HerdMaster Troubleshooting

This guide covers the implemented HerdMaster core: configuration, SQLite repositories, message bus, Herdr adapter, dispatch injector, and watchdog/recovery. It also maps PRD failure modes to the current fallback behavior.

Related design docs:

- [Technical design](TECHNICAL_DESIGN.md)
- `docs/architecture_macro.html`
- `docs/architecture_micro.html`
- `docs/architecture_deep.html`

## Quick Triage

1. Validate configuration before starting long-running tasks.
2. Confirm the SQLite DB opens and schema is initialized.
3. Confirm Herdr CLI commands work outside HerdMaster.
4. Confirm the message bus is either bound to its Unix socket or writing to its fallback file.
5. Confirm agents have `herdr_pane` values in the `agents` table before dispatch/recovery.
6. Check `health_events` for watchdog transitions and recovery attempts.

## Configuration Problems

### HerdMaster ignores my config file

`load_config()` uses `~/.config/herdmaster/config.toml` when no path is passed. If that file does not exist, defaults are used without error.

Check:

```bash
ls -l ~/.config/herdmaster/config.toml
```

Common fixes:

- Pass the intended config path to the runner that calls `load_config()`.
- Verify relative `[paths]` entries are resolved under `paths.config_dir`.
- Run validation after load; invalid values raise `ConfigError`.

### Config reload does not apply

`ConfigWatcher` polls mtime. It only calls the callback after a successful `load_config()` and `validate_config()`.

Common causes:

- The file mtime did not change.
- TOML is invalid.
- `watchdog.soft_timeout_s >= watchdog.hard_timeout_s`.
- `bus.message_ttl_s <= 0`.
- API port is outside `1..65535`.
- Duplicate ACL role names exist in config.

Bad reloads are logged and the previous config remains active.

## SQLite and WAL

### Database cannot be opened

`connect(db_path)` creates parent directories for normal paths and enables WAL, foreign keys, and a 5 second busy timeout.

Check:

```bash
ls -ld $(dirname ~/.config/herdmaster/herdmaster.db)
```

Fixes:

- Ensure the process user can create and write the config directory.
- Avoid placing the DB on a filesystem that does not support SQLite locking reliably.
- Call `init_db(conn)` before repository use.

### Frequent `database is locked`

The connection uses `PRAGMA busy_timeout=5000`, but write-heavy loops can still contend.

**Known cause (2026-06-25 — Webhook Server):** If a secondary process (e.g. remediation webhook)
opens a direct SQLite connection while HerdMaster holds a write lock, the result is `database is locked`
even with `busy_timeout`. The root cause is that HerdMaster is the exclusive writer and does not yield
the write lock between rapid-fire upserts.

**Correct fix:** Secondary processes must **never** access the SQLite DB directly. Use the HerdMaster
HTTP API (`DELETE /agents/{id}`, `PATCH /agents/{id}`, etc.) instead. HerdMaster serializes writes
through its own connection pool and transaction boundaries.

```python
# WRONG — causes database is locked
conn = sqlite3.connect(db_path, timeout=5)
conn.execute("DELETE FROM agents WHERE ...")

# CORRECT — goes through single DB owner
urllib.request.urlopen(Request(
    f"http://127.0.0.1:8080/agents/{agent_id}",
    method="DELETE",
    headers={"Authorization": "Bearer admin"},
))
```

Other fixes:

- Reuse repository instances and keep write transactions short.
- Avoid long-running manual transactions around repository calls; repository methods commit each write.
- Keep one dispatch claim loop per process where possible.
- If DB is locked after a crash: `sqlite3 $DB "PRAGMA wal_checkpoint(TRUNCATE);"` then `rm $DB-wal $DB-shm`.

### Phantom Agents Appearing in DB

**Symptom:** `herdmaster agents list` shows agents like `w8:p1`, `w8:p2`, etc. that are not part of the canonical registry.

**Root cause:** `WatchdogEngine._sync_agent()` previously called `AgentRepo.upsert()` for **every** pane
reported by `herdr agent list`, including panes from other Herdr workspaces (e.g. `w8`).

**Solution implemented (2026-06-25):** Allowlist guard in `watchdog/engine.py`:

```python
if self.config.agent_allowlist and agent.id not in self.config.agent_allowlist:
    log.debug("allowlist: ignoring unregistered Herdr pane %r", agent.id)
    return  # never reaches AgentRepo.upsert()
```

**Configuration** in `~/.config/herdmaster/config.toml`:
```toml
[watchdog]
agent_allowlist = ["cli", "w6:p1", "w6:p2", "w6:p5", "w6:p6", "w6:p7", "w6:p8"]
```

**If phantoms appear despite the allowlist** (e.g. direct SQLite injection):
1. Prometheus alert `UnlistedAgentsDetected` fires within 10s
2. Alertmanager routes to webhook at `localhost:9099`
3. Webhook calls `DELETE /agents/{id}` via HTTP API (~45s total)
4. DB returns to 7 canonical agents

**Manual purge (last resort):**
```bash
herdmaster agents list --json | python3 -c "
import sys, json, urllib.request
agents = json.load(sys.stdin)['data']
canonical = {'cli','w6:p1','w6:p2','w6:p5','w6:p6','w6:p7','w6:p8'}
for a in agents:
    if a['id'] not in canonical:
        urllib.request.urlopen(urllib.request.Request(
            f'http://127.0.0.1:8080/agents/{a[\"id\"]}',
            method='DELETE', headers={'Authorization': 'Bearer admin'}))
        print(f'Deleted: {a[\"id\"]}')
"
```


### Suspected corruption

PRD fallback calls for WAL checkpoint and restore. The current source does not implement automated backup/restore.

Operational response:

1. Stop HerdMaster processes that write the DB.
2. Preserve `herdmaster.db`, `herdmaster.db-wal`, and `herdmaster.db-shm`.
3. Run SQLite integrity checks with your operational tooling.
4. If rebuilding, restore agent state from `herdr agent list --json` and reinitialize schema with `init_db()`.

## Message Bus

### Unix socket fails to bind

`MessageBusServer.start()` unlinks a stale socket path, then calls `asyncio.start_unix_server()`. On `OSError`, it activates `FileFallbackBus` instead of crashing.

Expected fallback file:

```text
<bus.socket_path with suffix .fallback>
```

Fixes:

- Ensure the parent directory of `bus.socket_path` is writable.
- Remove stale sockets only when no HerdMaster process is using them.
- Check path length limits for Unix sockets on your OS.
- Monitor the `.fallback` file if the socket cannot be restored immediately.

### Messages are not delivered

Common causes:

- Subscriber did not send the JSON-RPC `register` frame with `params.agent_id`.
- Message `to` does not match a registered agent ID.
- `to = "group:name"` has no registered group members.
- Message expired before delivery.
- Subscriber queue exceeded `max_queue_size`; oldest messages are dropped under backpressure.

What to inspect:

- `messages.delivered` and `messages.acknowledged` in SQLite.
- Server logs for unparseable frames or persistence failures.
- Whether `_using_fallback` is active.

### File fallback grows quickly

`FileFallbackBus` truncates when the configured size limit is exceeded. If the file grows repeatedly, the socket path is likely still unavailable or subscribers are not connected.

Fixes:

- Restore socket binding.
- Drain and archive fallback content before truncation if audit retention matters.
- Confirm downstream consumers can parse newline-delimited `Message.to_json()` frames.

## Herdr Adapter

### Herdr commands time out or fail

All Herdr calls pass through `HerdrAdapter` and raise `HerdrError` on timeout, startup failure, non-zero exit, or invalid parser output.

Check commands manually:

```bash
herdr agent list --json
herdr pane list --json
herdr pane read <pane_id>
herdr agent wait <agent_id> --state idle --timeout 60
```

Fixes:

- Confirm `herdr` is on `PATH`, or instantiate `HerdrAdapter(herdr_bin="/path/to/herdr")`.
- Increase adapter timeout for slow environments.
- Ensure Herdr JSON contains recognizable agent/pane fields.
- If Herdr Socket API is unavailable, watchdog still works through CLI polling when `agent_list()` and `pane_read()` work.

### Parser returns `unknown` state

The parser recognizes `idle`, `working`, `blocked`, `done`, and `unknown`. Any other state normalizes to `unknown`.

Operational impact:

- Watchdog treats `unknown` as an active state for timeout evaluation.
- If Herdr introduces new state names, update parser tests and `KNOWN_STATES` in a source task.

## Dispatch and Prompt Injection

### Task is not dispatched

`DispatchInjector.dispatch()` requires the task to exist and be in `assigned` state. It skips tasks already `dispatched`, `in_progress`, or terminal.

Check:

- `tasks.state`
- `tasks.assigned_to`
- `agents.herdr_pane`
- Herdr `agent_wait` result

Fixes:

- Use `TaskQueue.claim_next(agent_id)` before dispatch.
- Ensure the assigned agent exists in `agents` and has a valid Herdr pane.
- If `herdr_pane` is missing, ensure `adapter.agent_list()` can resolve it.

### Agent is busy

If `agent_wait(..., state="idle")` fails, dispatch raises `AgentNotIdle` internally. The injector requeues the task once for later dispatch unless retries are exhausted.

Fixes:

- Let the dispatch loop pick the task up later.
- Increase `DispatchInjectorConfig.idle_timeout_s` if agents routinely take longer to become idle.
- Inspect `tasks.retry_count` and `tasks.max_retries`.

### Long prompt injection fails

Implemented fallback:

- Prompts over `file_fallback_threshold_chars` are written to a prompt file and the pane receives an instruction to read that file.
- Short prompts are chunked by `max_chunk_chars`; if chunked send fails, the injector clears current input and switches to the file fallback.

Check:

```text
DispatchInjectorConfig.fallback_dir
```

Fixes:

- Ensure fallback directory is writable.
- Lower `file_fallback_threshold_chars` for fragile terminals.
- Lower `max_chunk_chars` or increase `chunk_pace_s` if panes drop input.
- Confirm agents have filesystem access to the prompt file path.

## Watchdog and Recovery

### Agent becomes `suspect`

The watchdog marks an active agent `suspect` when no progress is observed beyond `watchdog.soft_timeout_s`. Active states are `working`, `blocked`, and `unknown`.

Progress means one of:

- Herdr state changes.
- Terminal output hash changes.
- Agent reaches resting state `idle` or `done`.

Expected audit:

```sql
select event_type, details, created_at
from health_events
where agent_id = '<agent_id>'
order by created_at;
```

### Agent becomes `unhealthy`

If no progress continues beyond `watchdog.hard_timeout_s`, watchdog transitions to `unhealthy` and then `recovering`.

Fixes:

- Confirm `soft_timeout_s < hard_timeout_s`.
- Confirm `pane_read` returns changing output when the terminal is active.
- Increase timeouts for long-running commands that do not print output.
- Prefer task prompts that produce periodic progress output.

### Recovery fails immediately

`RecoveryManager` requires:

- A pane ID from the caller or `agents.herdr_pane`.
- A spawn command from argument, injected `command_resolver`, or fields such as `spawn_command`, `command`, or `herdr_command` if present in the agent row.
- An injected task replayer/callable with a public replay method or callable behavior.

Current schema does not define `spawn_command`, so production composition should inject a command resolver.

Fixes:

- Provide `command_resolver(agent_id, agent_row) -> str`.
- Provide `task_replayer.replay_last_task(agent_id)` or equivalent supported method.
- Confirm `adapter.spawn_agent()` works for the target pane.
- Confirm `agent_wait()` reaches idle after respawn.

### Stuck agent escalates

After `watchdog.max_retries` consecutive recovery failures, recovery emits an `alert` `Message` through the injected bus publisher.

Operational response:

1. Inspect the alert payload for `agent_id`, failure count, and error.
2. Inspect `health_events` for the transition path.
3. Check the Herdr pane manually.
4. Decide whether to restart the agent manually, reassign the task, or cancel the task.

### Primary Herdr event source is unavailable

The current `HerdrAdapter` implements CLI methods only. `WatchdogEngine` attempts primary subscription only if the adapter instance exposes one of these async iterator methods:

- `subscribe_state_changes`
- `state_changes`
- `watch_state_changes`
- `watch_agents`

If none exists, or the primary source fails, the engine continues with secondary polling and tertiary output hashing. This is expected behavior, not a fatal condition.

## HerdMaster Process Crash

Herdr agents keep running independently if HerdMaster stops. Current code provides durable SQLite state, but no top-level supervisor is implemented in source.

Operational response:

1. Restart the process that composes bus, watchdog, and dispatch.
2. Reopen the same SQLite DB.
3. Re-register connected bus clients.
4. Let watchdog rediscover agents through `agent_list()`.
5. Requeue or inspect tasks left in `assigned`, `dispatched`, or `in_progress` according to your runbook.

## Testing Guidance

Source-aligned test areas:

- Config defaults, validation failures, and watcher bad-reload behavior.
- SQLite schema initialization and repository CRUD/state transitions.
- Message JSON-RPC round trips, TTL expiry, broadcast/unicast/group routing, and file fallback.
- Herdr adapter timeout/non-zero/invalid JSON behavior with mocked subprocesses.
- TaskQueue CAS claim and dependency ordering.
- Dispatch idle gating, chunking, file fallback, retries, and failed state updates.
- Watchdog healthy/suspect/unhealthy/recovering transitions, secondary-only polling, recovery success, and escalation alert.

PRD scenarios that require modules not present yet, such as project squad recommendation and TUI metrics, should be tested when those modules are implemented.

---

## Known Issues — Produção (2026-06-25)

### INC-P001 — `"agent 'cli' has no resolvable Herdr pane"`

**Status:** ✅ RESOLVIDO em 2026-06-25T15:22:42Z

**Sintoma:**
```
HerdrError: agent 'cli' has no resolvable Herdr pane
Task state → failed
```

**Causa raiz:**
O LLM planner atribuiu tasks a `assigned_to="cli"` (CLI Operator). O `DispatchInjector._resolve_pane_id()` (`injector.py:157`) exige `herdr_pane` para qualquer agente que receba task. O `cli` tem `herdr_pane=NULL` por design (`schema.py:17` — campo nullable).

O mesmo aconteceu para `Kiro_Opus-48` com `role="worker"` — o SquadRecommender podia incluí-lo em squads.

**Correção aplicada:**
```bash
sqlite3 ~/.config/herdmaster/herdmaster.db \
  "UPDATE agents SET role='orchestrator' WHERE id IN ('cli','w6:p7','w8:p6');"
```

**Prevenção:**
- `squad.py:33` filtra `role != "orchestrator"` antes de qualquer atribuição de task.
- Com `role=orchestrator`, o `cli` e o `Kiro` nunca entrarão em squads de execução.
- Para verificar: `sqlite3 ~/.config/herdmaster/herdmaster.db "SELECT id, role FROM agents WHERE role='orchestrator';"`

**Evidência de código:**
- `squad.py:33` — filtro de orchestrators no SquadRecommender
- `injector.py:146-157` — `_resolve_pane_id()` falha para agentes sem pane
- `schema.py:17` — `herdr_pane TEXT` (nullable by design)
- `ADR-001:75` — *"o seed `cli` cobre ações do operador"* — nunca executa tasks

---

### INC-P002 — Roles incorretos após criação do DB (role padrão genérico)

**Status:** ✅ RESOLVIDO em 2026-06-25T15:22:42Z

**Sintoma:** Agentes registrados pelo Herdr sync recebem `role="worker"` por padrão, incluindo Kiro.

**Causa raiz:** O Herdr sync popula o campo `role` sem diferenciar Kiro/orchestrators de workers. O `config.toml` não propagava o role correto para o DB automaticamente.

**Correção:** Executar UPDATE manual para orchestrators após cada sync ou flush. Ver `OPS_RUNBOOK.md §5`.

---

### INC-P003 — WAL acumulando após flush (checkpoint não executado)

**Status:** ✅ RESOLVIDO em 2026-06-25T14:57:21Z

**Sintoma:** `herdmaster.db-wal` com 4MB após `reset-hard`.

**Causa raiz:** O flush deleta e recria o DB, mas o WAL do SQLite pode acumular se o checkpoint não for forçado explicitamente.

**Correção:**
```bash
sqlite3 ~/.config/herdmaster/herdmaster.db 'PRAGMA wal_checkpoint(TRUNCATE);'
```

O `bootstrap.sh reset-hard` agora executa checkpoint após reset.

---

### INC-P004 — Aliases `hm-*` não disponíveis em shells não-interativos

**Status:** ✅ DOCUMENTADO (comportamento esperado do bash)

**Sintoma:** `hm-start: command not found` quando chamado via `wsl bash -c "hm-start"`.

**Causa:** Aliases do bash só são carregados em shells interativos (`-i`). Shells não-interativos não carregam `~/.bashrc`.

**Workaround:**
```bash
# Use o script diretamente em shells não-interativos:
bash /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/ops/bootstrap.sh start

# Ou force shell interativo:
wsl bash --login -i -c "hm-start"
```

---

## Referências Rápidas (2026-06-25)

- **Agent Registry:** [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md)
- **Communication Protocol:** [`COMMUNICATION_PROTOCOL.md`](COMMUNICATION_PROTOCOL.md)
- **OPS Runbook:** [`OPS_RUNBOOK.md`](OPS_RUNBOOK.md)
- **Architecture Decision:** [`ADR-001_acoplamento_Herdr_HerdMaster.md`](ADR-001_acoplamento_Herdr_HerdMaster.md)


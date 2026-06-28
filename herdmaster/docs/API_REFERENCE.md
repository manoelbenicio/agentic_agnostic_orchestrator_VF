# HerdMaster Control API Reference

This document describes the **Control API as actually implemented** in
`src/herdmaster/api/server.py` (`ControlApiServer`). Where the PRD §10 wish-list
and the shipped code differ, this document follows the code.

The Control API is a local control plane for driving Project Mode, the task
queue, agents, and the message bus. The **primary transport is a Unix domain
socket**; an **optional localhost-only HTTP listener** is available for tools
that cannot speak the socket protocol.

---

## 1. Transports & Envelopes

### 1.1 Unix domain socket (primary)

- Path: `config.paths.socket` (or the `socket_path` passed to the server).
- Framing: **newline-delimited JSON** — one JSON request object per line, one
  JSON response object per line.
- The socket is the trusted, primary control channel and performs **no token
  authentication** (filesystem permissions on the socket are the access
  boundary). Message sends are still subject to ACL checks (see §3).

A request line may use either of two envelopes:

**HTTP-like envelope**

```json
{"method": "GET", "path": "/status", "body": {}, "query": {}}
```

- `method` — HTTP verb (`GET`, `POST`, `PATCH`, `DELETE`, or `STREAM`).
- `path` — route, e.g. `/projects/proj-1/tasks`. A query string in `path` is
  parsed; an explicit `query` object is merged on top.
- `body` — request payload object (defaults to `{}`).
- `id` — optional. When present, the response is wrapped in a JSON-RPC envelope
  (see §1.3).

**JSON-RPC-style envelope**

```json
{"jsonrpc": "2.0", "method": "GET /status", "params": {}, "id": 1}
```

- `method` contains `"<VERB> <path>"` (a space separates verb and path).
- `params` is used as the request body (and may also carry `path`).
- `id` — when present, the response is a JSON-RPC result/error envelope.

> Parsing rule (`_socket_request`): if `method` contains a space it is split into
> `method` + `path` and `params` becomes the body. Otherwise `method` is the verb
> and `path`/`body` are read from the top-level fields (falling back to `params`).

### 1.2 HTTP (optional, localhost-only)

- Enabled with `http_enabled=True`; binds to `config.api.bind` and
  `config.api.port`.
- **Startup is refused unless** `config.api.bind` is one of `127.0.0.1`,
  `localhost`, or `::1`, **and** `config.api.token` is non-empty
  (`_validate_security`). HTTP without a token is never served.
- Every HTTP request must send `Authorization: Bearer <api.token>`; otherwise
  the server responds `401 unauthorized` (see §3).
- Request bodies are JSON (`Content-Type: application/json`, `Content-Length`
  honored). The route and verb come from the HTTP request line; the query string
  is parsed from the target.
- One request per connection; the server replies with `Connection: close`.

### 1.3 Response envelopes

**Plain response** (socket request with no `id`, or any HTTP request):

```json
{"ok": true, "data": { ... }}
```

**JSON-RPC response** (socket request that included an `id`):

```json
{"jsonrpc": "2.0", "id": 1, "result": {"ok": true, "data": { ... }}, "error": null}
```

On error with an `id`, `result` is `null` and `error` carries the error object
(see §4):

```json
{"jsonrpc": "2.0", "id": 1, "result": null, "error": {"code": "not_found", "message": "project not found"}}
```

---

## 2. Endpoints

All routes are dispatched in `_dispatch`. Routes that exist as a prefix but are
called with an unsupported method/shape return **`405 method_not_allowed`**;
completely unknown prefixes return **`404 not_found`**.

### 2.1 Projects (Project Mode)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects` | Create + analyze a project (awaiting approval). |
| `GET` | `/projects` | List projects (optional `?state=`). |
| `GET` | `/projects/:id` | Project detail + child tasks + progress. |
| `PATCH` | `/projects/:id` | Update state **or** approve/modify/override. |
| `DELETE` | `/projects/:id` | Cancel project and its non-terminal tasks. |
| `POST` | `/projects/:id/approve` | Approve squad + ETA, decompose & enqueue tasks. |
| `GET` | `/projects/:id/eta` | Recompute the live ETA estimate. |
| `GET` | `/projects/:id/tasks` | List tasks belonging to the project. |

**`POST /projects` — request**

```json
{
  "name": "User Authentication System",
  "scope": "Build a complete user auth system with JWT...",
  "deadline": "2026-06-25T18:00:00Z",
  "created_by": "human",
  "template": "feature",
  "orchestrator_id": "A1",
  "orchestrator_output": "{...optional pre-computed analysis JSON...}"
}
```

- `name` is required. The scope is read from `scope` **or** `full_scope_prompt`;
  one of them must be non-empty (else `400 bad_request`).
- `deadline`, `created_by`, `template`, `orchestrator_id`, `orchestrator_output`
  are optional. When `orchestrator_output` is omitted the planner injects the
  analysis prompt into the orchestrator pane via the dispatcher and reads the
  result back; when provided, that JSON is used directly.
- Response `data` is the **project detail** object (see below), with the project
  in state `awaiting_approval`.

**`GET /projects/:id` — response `data`** (`_project_detail`)

```json
{
  "ok": true,
  "data": {
    "id": "proj-...",
    "name": "User Authentication System",
    "state": "awaiting_approval",
    "scope": "Build a complete user auth system...",
    "deadline": "2026-06-25T18:00:00Z",
    "analysis": {
      "complexity_tier": "L",
      "squad": [{"agent": "A4", "role": "lead_implementer", "rationale": "..."}],
      "eta": {
        "optimistic_hours": 1.5,
        "expected_hours": 2.5,
        "pessimistic_hours": 4.0,
        "rationale": "14 tasks, critical path depth 4, ..."
      },
      "tasks_preview": [{"title": "Database schema", "assigned_to": "A2", "priority": "critical"}],
      "raw": { "...": "raw orchestrator analysis" }
    },
    "progress": {
      "total_tasks": 14, "completed": 0, "in_progress": 0,
      "failed": 0, "percent_complete": 0.0
    },
    "tasks": [ { "...task rows..." } ],
    "created_at": "2026-06-21 23:00:00",
    "updated_at": "2026-06-21 23:00:00"
  }
}
```

> `GET /projects` returns a lighter **summary** per project: `id`, `name`,
> `state`, `complexity_tier`, `eta_expected_hours`, `progress`, `created_at`,
> `updated_at`.

**`PATCH /projects/:id`** has two modes, decided by the body:

- If `body.state` is present → updates the raw project state and returns the
  project detail. `404 not_found` if the project does not exist.
- Otherwise → treated as an **approval** (same as `POST .../approve`):

```json
{
  "decision": "accept",
  "squad": [{"agent": "A4", "role": "lead_implementer", "rationale": "..."}],
  "eta": {"optimistic_hours": 1.5, "expected_hours": 2.5, "pessimistic_hours": 4.0, "rationale": "..."},
  "assignments": [{"title": "...", "prompt": "...", "assigned_to": "A2", "depends_on": [], "priority": "high"}],
  "human_notes": "swap A5 for A2"
}
```

- `decision` is `accept` (default), `modify`, or `override`.
- `squad`, `eta`, `assignments` are optional and only used when the right type
  (list/dict). On `override` (or `modify` with `assignments`) the supplied
  `assignments` become the task breakdown.
- Response `data`:

```json
{"ok": true, "data": {"project": { ...project detail... }, "task_ids": ["task-...", "task-..."]}}
```

Approval enqueues the project's tasks in **topological (dependency) order**,
sets the project to `approved` then `in_progress`.

**`POST /projects/:id/approve`** — identical body and response to the approval
mode of `PATCH`.

**`DELETE /projects/:id`** — cancels every non-terminal child task via the queue
and sets the project state to `cancelled`. Returns the project detail.

**`GET /projects/:id/eta` — response `data`** (recomputed live via
`EtaEstimator`):

```json
{
  "ok": true,
  "data": {
    "optimistic_hours": 1.5,
    "expected_hours": 2.5,
    "pessimistic_hours": 4.0,
    "rationale": "12 tasks, critical path depth 3, parallelism 3, ..."
  }
}
```

**`GET /projects/:id/tasks` — response `data`** is the array of task rows for the
project (`TaskRepo.list(project_id=...)`).

### 2.2 Tasks

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tasks` | Enqueue a task (standalone or under a project). |
| `GET` | `/tasks` | List tasks (filters: `state`, `assigned_to`, `project_id`). |
| `GET` | `/tasks/:id` | Task detail. |
| `PATCH` | `/tasks/:id` | Cancel, reassign, or set state. |
| `DELETE` | `/tasks/:id` | Cancel the task. |

**`POST /tasks` — request**

```json
{
  "title": "Implement parser",
  "prompt": "Write the parser and tests",
  "project_id": "proj-1",
  "description": "optional",
  "priority": "high",
  "assigned_to": "A2",
  "depends_on": ["task-abc"],
  "created_by": "A1",
  "max_retries": 3,
  "timeout_seconds": 1800
}
```

- `title` and `prompt` are required (`400 bad_request` otherwise).
- `priority` accepts the strings `critical|high|normal|low` (default `normal`)
  or an integer; `assigned_to` also accepts the alias `agent`.
- Response `data` is the created task row (`TaskRepo.get`).

**`GET /tasks` — response `data`** is the list of task rows matching the query
filters.

**`PATCH /tasks/:id`** (`_patch_task`), decided by the body:

- `{"action": "cancel"}` or `{"state": "cancelled"}` → cancels via the queue,
  returns the cancelled task row.
- `{"action": "reassign"}` → retries/escalates via the queue; returns:

  ```json
  {"ok": true, "data": {"task_id": "task-1", "reassigned": true, "escalated": false, "retry_count": 1, "max_retries": 3}}
  ```

- `{"state": "<state>"}` → sets the task state directly, returns the task row
  (`404 not_found` if unknown).
- Otherwise → `400 bad_request` ("task patch requires action or state").

**`DELETE /tasks/:id`** → cancels the task via the queue, returns the cancelled
task row.

### 2.3 Agents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/agents` | List agents (each with its current in-progress task). |
| `GET` | `/agents/:id` | Agent detail (with current task). |
| `POST` | `/agents/:id/message` | Send a message addressed to the agent (ACL-gated). |
| `POST` | `/agents/:id/restart` | Trigger an agent restart/recovery. |
| `GET` | `/agents/:id/health` | Agent health snapshot. |
| `GET` | `/agents/:id/metrics` | Agent performance metrics. |

**`GET /agents` / `GET /agents/:id` — response `data`** is the agent row plus a
`current_task` field (the agent's `in_progress` task row, or `null`).
`404 not_found` for an unknown agent id.

**`POST /agents/:id/message`** — the path agent becomes the `to`; the rest of
the body matches `POST /messages` (see §2.4). ACL-gated (`403 acl_denied`).

**`POST /agents/:id/restart` — intended response `data`**

```json
{"ok": true, "data": {"agent": "A1", "state": "recovering", "message_id": "..."}}
```

- `404 not_found` for an unknown agent (this check runs first and works).
- Intended behavior: if a restart hook was configured, return its result under
  `result`; otherwise mark the agent `recovering` (state + health) and broadcast
  an `alert` message, returning `message_id`.

> **⚠️ Known issue (as committed):** for an **existing** agent this endpoint
> currently raises `500 internal_error`. `_restart_agent` references
> `self.restart_agent`, but the constructor stores the hook as
> `self.restart_agent_hook` and no `restart_agent` attribute exists, so the
> attribute access fails before either branch runs. The `404` path for unknown
> agents is unaffected. Tracked for the API owner (HM-011); not corrected here
> (docs-only task).

**`GET /agents/:id/health` — response `data`**

```json
{"ok": true, "data": {"agent": "A1", "state": "working", "health": "healthy", "last_heartbeat": "2026-06-21 23:00:00"}}
```

**`GET /agents/:id/metrics` — response `data`**

```json
{
  "ok": true,
  "data": {
    "agent": "A1",
    "avg_task_seconds": 120,
    "tasks_completed": 5,
    "tasks_assigned": 7,
    "tasks_failed": 1,
    "failure_rate": 0.142,
    "last_heartbeat": "2026-06-21 23:00:00"
  }
}
```

### 2.4 Messages

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/messages` | Send a message through the bus (ACL-gated). |
| `GET` | `/messages` | List messages (filters: `to_agent`/`to`, `delivered`). |
| `GET` / `STREAM` | `/messages/stream` | Real-time message stream (see §5). |

**`POST /messages` — request**

```json
{
  "from_agent": "A1",
  "to": "A2",
  "type": "chat",
  "payload": {"text": "hello"},
  "correlation_id": null,
  "ttl_seconds": 300
}
```

- `from_agent` (alias `from`) and `to` are required.
- `type` defaults to `chat`; valid types are `task_assign`, `task_update`,
  `heartbeat`, `chat`, `alert`, `state_change`.
- If `payload` is not an object, the server wraps `text` as `{"text": "..."}`.
- The message is checked against the ACL engine **before** sending; a denied
  send returns `403 acl_denied` with `details: {from_agent, to}`.
- Response `data` is the sent message:

```json
{
  "ok": true,
  "data": {
    "id": "...", "type": "chat", "from_agent": "A1", "to": "A2",
    "correlation_id": null, "timestamp": "2026-06-21T23:00:00Z",
    "ttl_seconds": 300, "payload": {"text": "hello"}
  }
}
```

**`GET /messages` — response `data`** is the list of stored message rows.
`?delivered=true|false` filters by delivery state; `?to_agent=` / `?to=` filters
by recipient.

**`GET|STREAM /messages/stream`** — when called as a normal request (not a stream
upgrade) returns a descriptor: `{"ok": true, "data": {"stream": "messages",
"transport": "newline-json"}}`. The live streaming behavior is described in §5.

### 2.5 System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | System health + uptime. |
| `GET` | `/metrics` | Prometheus-format metrics (text). |
| `POST` | `/config/reload` | Hot-reload + revalidate configuration. |

**`GET /status` — response `data`**

```json
{
  "ok": true,
  "data": {
    "state": "running",
    "uptime_seconds": 132,
    "started_at": "2026-06-21T23:00:00Z",
    "agents": {"total": 3, "unhealthy": 0},
    "tasks": {"queued": 2, "in_progress": 1, "done": 5},
    "projects": {"total": 1},
    "transports": {"unix": "/path/herdmaster.sock", "http": false, "http_bind": "127.0.0.1", "http_port": 8080}
  }
}
```

(`tasks` is a per-state count map.)

**`GET /metrics`** — returns Prometheus text. Over HTTP the body is served as
`Content-Type: text/plain; version=0.0.4`. Over the socket the response is the
JSON object `{"ok": true, "content_type": "text/plain; version=0.0.4", "data":
"<prometheus text>"}`. Exposed series:

```
herdmaster_agents_total <n>
herdmaster_projects_total <n>
herdmaster_tasks_total{state="<state>"} <n>
herdmaster_agent_tasks_completed_total <n>
```

**`POST /config/reload` — request** `{"path": "/optional/path/to/config.toml"}`.
Loads and validates the config, hot-swaps the ACL config, and invokes the
optional reload hook. Invalid config → `400 config_error`. Response:

```json
{"ok": true, "data": {"reloaded": true, "path": "/optional/path", "hook_result": null}}
```

---

## 3. Security Model

- **Unix socket is primary and unauthenticated at the protocol level.** Access
  is controlled by filesystem permissions on the socket path. This is the
  intended channel for trusted local orchestration.
- **HTTP is optional, localhost-only, and token-required.** `start()` calls
  `_validate_security()`, which:
  - raises `ValueError` unless `api.bind` ∈ {`127.0.0.1`, `localhost`, `::1`};
  - raises `ValueError` if HTTP is enabled but `api.token` is empty.
- **HTTP auth**: every request must carry `Authorization: Bearer <api.token>`.
  A missing/incorrect token yields `401 unauthorized` (`{"ok": false, "error":
  {"code": "unauthorized", "message": "bearer token required"}}`).
- **ACL-gated message sends**: `POST /messages` and `POST /agents/:id/message`
  build a `Message` and call `AclEngine.check_message`. A policy denial raises
  `AclDenied`, surfaced as `403 acl_denied` with
  `details: {from_agent, to}`. Other endpoints are not ACL-gated.

---

## 4. Errors

Errors are raised as `ApiError(status, code, message, details=None)` and
serialized as:

```json
{"ok": false, "error": {"code": "<code>", "message": "<message>", "details": <optional>}}
```

Over HTTP the HTTP status equals `status`. Over the socket the payload is
returned as-is for requests without an `id`, or wrapped in the JSON-RPC `error`
field when an `id` was supplied.

| Status | Code | When |
|--------|------|------|
| 400 | `bad_json` | Socket request body is not valid JSON. |
| 400 | `bad_request` | Missing required field, or non-object request, or invalid task patch, or missing project scope. |
| 400 | `config_error` | `POST /config/reload` with invalid configuration. |
| 401 | `unauthorized` | HTTP request without a valid `Bearer` token. |
| 403 | `acl_denied` | Message send blocked by the ACL engine. |
| 404 | `not_found` | Unknown endpoint, or referenced project/task/agent does not exist. |
| 405 | `method_not_allowed` | Known route prefix called with an unsupported method or path shape (e.g. `PUT /tasks/:id`, `GET /projects` sub-routes that don't exist). |
| 500 | `internal_error` | Unhandled server-side exception. |

> **405 pattern**: each route handler (`_projects`, `_tasks`, `_agents`,
> `_messages`) falls through to `raise ApiError(405, "method_not_allowed", ...)`
> when no method/shape inside that resource matches. A request whose top-level
> resource is unknown returns `404 not_found` instead.

---

## 5. Streaming `/messages/stream`

The server streams new message rows roughly once per second, tracking already
seen message ids so each row is sent once. Three modes are supported:

- **Unix socket** — send a request with `method: "STREAM"` and
  `path: "/messages/stream"`. The server then writes newline-delimited JSON
  frames:

  ```json
  {"ok": true, "event": "message", "data": { ...message row... }}
  ```

- **HTTP (NDJSON)** — `GET /messages/stream` (with the bearer token) and without
  an `Upgrade` header. The server responds `200 OK` with
  `Content-Type: application/x-ndjson` and streams one JSON object per line.

- **HTTP WebSocket** — `GET /messages/stream` with `Upgrade: websocket` and a
  valid `Sec-WebSocket-Key`. The server completes the RFC6455 handshake
  (`101 Switching Protocols`) and emits each event as a WebSocket text frame.

Streams end when the client disconnects or the server stops; active stream tasks
are cancelled cleanly on shutdown.

---

## 6. Notes & Cross-References

- Message schema and types: `src/herdmaster/bus/messages.py`
  (`Message`, `MessageType`).
- ACL semantics: `src/herdmaster/acl/engine.py` (`AclEngine`, `AclDenied`).
- Task lifecycle and priorities: `src/herdmaster/dispatch/queue.py`
  (`TaskQueue`, priority map `critical=0, high=1, normal=2, low=3`).
- Project Mode workflow and ETA: `src/herdmaster/project/`
  (`planner.py`, `eta.py`, `squad.py`).
- Config (`api.bind`, `api.port`, `api.token`, `bus.message_ttl_s`, socket
  path): `src/herdmaster/config.py`.

This reference reflects `src/herdmaster/api/server.py` as committed. Endpoint
shapes, error codes, and the security model above were verified against the
route-dispatch code in `_dispatch`, `_projects`, `_tasks`, `_agents`,
`_messages`, `_status`, `_prometheus_metrics`, and `_reload_config`.

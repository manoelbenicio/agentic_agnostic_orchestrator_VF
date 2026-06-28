# 37 — API Reference (OpenAPI/Swagger)

> **Spec fonte:** [`openapi.json`](openapi.json) — gerado por
> `scripts/generate_openapi.py` a partir de `control-plane/app/main.py`.
>
> **Versão OpenAPI:** 3.1.0 · **50 paths** · **46 schemas**
>
> Para visualização interativa, carregue `openapi.json` em
> [Swagger Editor](https://editor.swagger.io/) ou sirva via
> `http://127.0.0.1:8090/docs` (Swagger UI nativo do FastAPI).

---

## Regeneração do spec

```bash
PYTHONPATH=control-plane:../HerdMaster/src \
  /tmp/aop-control-plane-venv/bin/python scripts/generate_openapi.py
```

O script importa `create_app()`, chama `app.openapi()` e grava em
`docs/30-COMPONENTES/openapi.json`. Execute após adicionar/remover rotas.

---

## Endpoints por categoria

### Health & Observability

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/health` | Liveness + coupling status (HerdMaster) |
| GET | `/health/ready` | Readiness: Postgres + Redis + coupling |
| GET | `/metrics` | Métricas Prometheus (liveness, finops, tracing) |

### Agents

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/agents` | Listar agentes registrados |
| POST | `/agents` | Criar agente (label, vendor, role, pane) |
| DELETE | `/agents/{agent_id}` | Remover agente por ID |

### Tasks (dispatch dual-mode)

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/tasks` | Listar tasks |
| POST | `/tasks` | Criar e despachar task (terminal/socket) |
| GET | `/tasks/board` | Board agregado: % progresso, ETA, contagem por status |
| GET | `/tasks/herdmaster` | Proxy: listar tasks ao vivo no HerdMaster |
| POST | `/tasks/reconcile` | Reconciliar squad-tasks.json ↔ Postgres ↔ HerdMaster |
| GET | `/tasks/{task_id}` | Obter task por ID |
| PATCH | `/tasks/{task_id}` | Atualizar status/progress/eta/herdmaster_state |

### Issues

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/issues` | Listar issues (filtros: tenant, project, status, assignee) |
| POST | `/issues` | Criar issue |
| GET | `/issues/my` | Issues relevantes ao agente (X-Agent-Id header) |
| DELETE | `/issues/{issue_id}` | Soft-delete de issue |
| GET | `/issues/{issue_id}` | Obter issue por ID |
| PATCH | `/issues/{issue_id}` | Atualizar issue |
| POST | `/issues/{issue_id}/dispatch` | Despachar issue como task |

> Rotas espelhadas sob `/api/issues` (mesma implementação, prefixo alternativo).

### Projects

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/projects` | Listar projetos |
| POST | `/projects` | Criar projeto |
| DELETE | `/projects/{project_id}` | Remover projeto |
| GET | `/projects/{project_id}` | Obter projeto por ID |
| PATCH | `/projects/{project_id}` | Atualizar projeto |

### Squads & Topology

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/squads/{squad_id}/topology` | Obter topologia armazenada + ACL efetiva |
| POST | `/squads/{squad_id}/topology` | Salvar topologia (nodes + edges → ACL) |
| POST | `/squads/{squad_id}/messages` | Roteamento de mensagem runtime (validado por ACL) |

### FinOps

| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/finops/costs/token` | Registrar custo de tokens (input/output, preço) |
| POST | `/finops/costs/seat` | Registrar custo de seat (tempo usado, período) |
| GET | `/finops/projects/{tenant_id}/{project_id}/rollup` | Rollup de custos por projeto |
| GET | `/finops/projects/{tenant_id}/{project_id}/rollup/{dimension}` | Breakdown por dimensão (model, issue_id, agent_id, runtime_id) |

### Tracing

| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/tracing/events` | Registrar evento de trace |
| POST | `/tracing/artifacts` | Registrar artefato de sessão |
| GET | `/tracing/agents/{agent_id}` | Timeline de eventos por agente |
| GET | `/tracing/runtimes/{runtime_id}` | Timeline de eventos por runtime |

### Inbox

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/inbox` | Listar eventos de inbox |
| POST | `/inbox` | Criar evento de inbox |
| GET | `/inbox/unread-count` | Contagem de eventos não lidos |
| POST | `/inbox/{event_id}/read` | Marcar evento como lido |
| POST | `/inbox/bulk-archive` | Arquivar eventos em lote |

### Seats

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/seats` | Listar seats |
| POST | `/seats` | Criar seat |
| DELETE | `/seats/{seat_id}` | Remover seat |
| GET | `/seats/{seat_id}` | Obter seat por ID |
| PATCH | `/seats/{seat_id}` | Atualizar seat |

### Sessions

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/sessions` | Listar sessões |
| POST | `/sessions/device-login` | Login via device (OAuth/CLI) |
| GET | `/sessions/{session_id}/status` | Status de sessão |
| POST | `/sessions/{session_id}/renew` | Renovar sessão |

### Settings

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/settings` | Obter configurações |
| PATCH | `/settings` | Atualizar configurações |
| GET | `/settings/profile` | Obter perfil |
| PATCH | `/settings/profile` | Atualizar perfil |
| GET | `/settings/integrations` | Listar integrações |
| POST | `/settings/integrations` | Criar/configurar integração |
| GET | `/settings/api-tokens` | Listar API tokens |
| POST | `/settings/api-tokens` | Criar API token |
| DELETE | `/settings/api-tokens/{id}` | Revogar API token |

---

## Schemas principais

### TaskCreateRequest
```json
{
  "task_id": "string",
  "tenant_id": "string",
  "project_id": "string",
  "issue_id": "issue-default",
  "assignee_runtime": "string",
  "prompt": "string",
  "credential_ref": "seat://local",
  "operation_mode": "terminal | socket",
  "seat_seconds": 0,
  "timeout_seconds": null,
  "account_id": null
}
```

### TaskResponse (OTTL)
```json
{
  "task_id": "string",
  "title": "string",
  "priority": "P0 | P1 | P2",
  "agent": "string",
  "pane": "string",
  "status": "pending | working | review | held | blocked | orphaned | done",
  "eta_min": 0,
  "progress": 0,
  "herdmaster_task_id": null,
  "herdmaster_state": null,
  "metadata": {},
  "created_at": "2026-06-27T22:00:00Z",
  "updated_at": "2026-06-27T22:00:00Z",
  "last_seen_at": "2026-06-27T22:00:00Z"
}
```

### BoardResponse (OTTL)
```json
{
  "total_tasks": 0,
  "done": 0,
  "overall_progress": 0.0,
  "total_eta_min": 0,
  "by_status": {
    "done": {"count": 0, "avg_progress": 100.0, "total_eta_min": 0},
    "working": {"count": 0, "avg_progress": 0.0, "total_eta_min": 0}
  }
}
```

### IssueCreateRequest
```json
{
  "issue_id": null,
  "tenant_id": "string",
  "project_id": "string",
  "title": "string",
  "description": null,
  "status": "backlog",
  "priority": "medium",
  "assignee_runtime": null,
  "operation_mode": "terminal",
  "due_date": null,
  "metadata": {}
}
```

### IssueResponse
```json
{
  "issue_id": "string",
  "tenant_id": "string",
  "project_id": "string",
  "title": "string",
  "description": null,
  "status": "backlog | todo | in_progress | blocked | done",
  "priority": "low | medium | high | critical",
  "assignee_runtime": null,
  "operation_mode": "terminal | socket",
  "due_date": null,
  "metadata": {},
  "created_at": "2026-06-27T22:00:00Z",
  "updated_at": "2026-06-27T22:00:00Z",
  "deleted_at": null
}
```

### TokenCostRequest
```json
{
  "tenant_id": "string",
  "project_id": "string",
  "issue_id": "string",
  "agent_id": "string",
  "runtime_id": "string",
  "input_tokens": 0,
  "output_tokens": 0,
  "input_token_price_usd": "0.0",
  "output_token_price_usd": "0.0",
  "model": "string",
  "trace_id": null
}
```

### TraceEventRequest
```json
{
  "trace_id": "string",
  "layer": "string",
  "signal_type": "string",
  "tenant_id": "string",
  "project_id": "string",
  "issue_id": "string",
  "agent_id": "string",
  "runtime_id": "string",
  "message": "string",
  "token_burn": 0,
  "seat_seconds": 0,
  "details": {}
}
```

---

## Autenticação

O control-plane aceita os seguintes headers em rotas que requerem identidade de agente:

| Header | Uso |
|--------|-----|
| `X-Agent-Id` | Identidade do agente chamador (issues/my, inbox) |
| `Authorization: Bearer <token>` | Token do HerdMaster (injetado via `HERDMASTER_TOKEN`) |

> Rotas internas (`/health`, `/metrics`, `/agents`, `/tasks`) não exigem
> autenticação no modo de desenvolvimento. Em produção, proteger via
> reverse proxy ou middleware de auth.

---

## CORS

Origens permitidas (configuráveis via `AOP_CORS_ORIGINS`):

- `http://127.0.0.1:13000`
- `http://localhost:13000`

---

## WebSocket

| Path | Descrição |
|------|-----------|
| `ws://127.0.0.1:8090/ws/tracing/agents/{agent_id}` | Stream de eventos de trace em tempo real para um agente |

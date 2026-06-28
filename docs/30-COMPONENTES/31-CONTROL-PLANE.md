# 31 — Control-Plane (FastAPI)

Origem da verdade: `control-plane/app/main.py` (+ `app/dependencies.py`, `app/schemas.py`, `app/settings.py`).

## 1. Visão geral

App FastAPI criado por `create_app()` (factory) com `lifespan` que constrói/derruba o `AppState` (conexões Postgres, cliente Redis, serviços de registry/topology/finops/tracing, message bus). Sobe via:

```
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Middleware: **CORS** com `allow_origins = effective_settings.cors_origins`, credentials, métodos e headers liberados.

Routers montados (além dos endpoints diretos):
`build_projects_router`, `build_issues_router`, `build_settings_router`, `build_inbox_router`, `seats_router`, `sessions_router`.

---

## 2. Endpoints (verificados em `main.py`)

### Saúde
| Método | Rota | Retorno |
|--------|------|---------|
| GET | `/health` | `{"status":"ok","coupling": {...}}` — inclui status do coupling com HerdMaster |
| GET | `/health/ready` | checa Postgres (`SELECT 1`) + Redis (`ping`); 503 se algum falhar |

> ⚠️ **`/health` retorna também `coupling`** (não só `{"status":"ok"}`). Isso quebra a asserção atual do smoke E2E — ver [`40-VERIFICACAO/41-SMOKE-E2E.md`](../40-VERIFICACAO/41-SMOKE-E2E.md).

### Tarefas e squads
| Método | Rota | Função |
|--------|------|--------|
| POST | `/tasks` | cria `TaskEnvelope` e coleta eventos do ciclo de vida (dispatch dual-mode) |
| POST | `/squads/{squad_id}/topology` | salva topologia (nós/arestas) e devolve ACL efetiva |
| GET | `/squads/{squad_id}/topology` | recupera topologia armazenada |
| POST | `/squads/{squad_id}/messages` | roteia mensagem runtime entre agentes (valida ACL) |

`POST /squads/{id}/messages` pode retornar **403 `topology_violation`** (viola ACL) ou **503 `message_bus_unavailable`** (HerdMaster indisponível) — ambos com `trace_id` e `audit_event_id`.

### Agentes (registry)
| Método | Rota | Função |
|--------|------|--------|
| POST | `/agents` | registra agente (tenant, label, vendor, role, pane opcional); 503 se propagação ao registry indisponível |
| GET | `/agents` | lista agentes |
| DELETE | `/agents/{agent_id}` | remove agente; 404 se inexistente |

### FinOps
| Método | Rota | Função |
|--------|------|--------|
| POST | `/finops/costs/token` | registra custo por tokens (input/output × preço, + `model`) |
| POST | `/finops/costs/seat` | registra custo por seat (utilização de assinatura) |
| GET | `/finops/projects/{tenant_id}/{project_id}/rollup` | agrega custo do projeto (token vs seat) |

Detalhes do cálculo em [`35-FINOPS-E-CUSTOS.md`](35-FINOPS-E-CUSTOS.md).

### Tracing (observabilidade de execução)
| Método | Rota | Função |
|--------|------|--------|
| POST | `/tracing/events` | registra evento de trace (layer, signal_type, burn de token, seat_seconds) |
| POST | `/tracing/artifacts` | registra artefato de sessão (URI) |
| GET | `/tracing/agents/{agent_id}` | timeline por agente |
| WS | `/ws/tracing/agents/{agent_id}` | stream em tempo real de eventos novos do agente |
| GET | `/tracing/runtimes/{runtime_id}` | timeline por runtime |

### Métricas
| Método | Rota | Função |
|--------|------|--------|
| GET | `/metrics` | texto Prometheus: `aop_control_plane_up`, FinOps (tenant/projeto **fixos** `tenant-a`/`project-a`), burn de tracing |

> Os routers montados adicionam ainda as áreas `projects`, `issues`, `settings`, `inbox`, `seats`, `sessions` (rotas definidas em seus respectivos módulos `*_api`). Para o mapa completo, consulte o Swagger em runtime: `http://127.0.0.1:8090/docs`.

---

## 3. WebSocket de tracing (detalhe)

`/ws/tracing/agents/{agent_id}` aceita a conexão, envia os eventos já existentes e depois faz polling do timeline a cada ~1s (`asyncio.wait_for(receive_text, timeout=1.0)`), enviando apenas eventos **novos** (dedup por `event_id`). Encerra em `WebSocketDisconnect`. É o que alimenta a página `/live` do frontend.

---

## 4. AppState e coupling

`build_state(settings)` monta as conexões e serviços. `_coupling_health(state)`:
- Sem `herdmaster_token` → `coupling.status = "degraded"`, desativa o message bus.
- Com token → faz `herdmaster_authenticated_probe`; se ok, instancia `HerdMasterHttpMessageBus` e marca `connected`.

Ver [`33-COUPLING-HERDMASTER-HERDR.md`](33-COUPLING-HERDMASTER-HERDR.md).

---

## 5. Verificação

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool
curl -s http://127.0.0.1:8090/health/ready | python3 -m json.tool
curl -s http://127.0.0.1:8090/openapi.json | python3 -c "import sys,json;d=json.load(sys.stdin);print('\n'.join(sorted(d['paths'])))"
# Criar um agente de teste:
curl -s -X POST http://127.0.0.1:8090/agents -H 'Content-Type: application/json' \
  -d '{"tenant_id":"t1","label":"TL","vendor":"codex","role":"orchestrator"}' | python3 -m json.tool
```

> A lista de paths via `/openapi.json` é a forma canônica de confirmar **todas** as rotas (incluindo as dos routers) sem depender desta tabela.

# 📡 Protocolo de Comunicação — HerdMaster
**Versão:** 2026-06-25 | **Fonte:** código-fonte verificado em `src/herdmaster/`

---

## 1. Visão Geral da Arquitetura de Comunicação

```
┌─────────────────────────────────────────────────────────────────────┐
│                      OPERADOR / VOCÊ                                 │
│              (via CLI: herdmaster projects create/approve)           │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP REST (127.0.0.1:8080)
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   HerdMaster Control Plane (PID=daemon)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  ACL Engine  │  │  MessageBus  │  │  DispatchInjector        │  │
│  │ default:DENY │  │ JSON-RPC 2.0 │  │  (prompt → Herdr pane)   │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│         │ valida          │ roteia                 │ injeta         │
│         └────────────────►│◄───────────────────────┘               │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ Unix Socket (~/.config/herdr/herdr.sock)
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Herdr Daemon                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ AGY_Opus-46  │  │  Codex_#1   │  │ AGY_Flash35  │  ...         │
│  │   w6:p1      │  │   w6:p5     │  │   w6:p8      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Message Bus — Especificação Técnica

**Arquivo:** [`bus/server.py`](../src/herdmaster/bus/server.py) + [`bus/messages.py`](../src/herdmaster/bus/messages.py)

| Atributo | Valor |
|---------|-------|
| Protocolo | JSON-RPC 2.0 (newline-delimited) |
| Transporte | Unix Domain Socket (`herdmaster.sock`) |
| Fallback | Arquivo `.fallback` em disco (zero perda de mensagem) |
| TTL padrão | 300 segundos |
| TTL sweep | A cada 30 segundos (automático) |
| Persistência | Toda mensagem gravada no DB antes de ser roteada |
| Backpressure | Queue por agente (1024 slots) — oldest-drop para manter <500ms |

### Tipos de endereçamento

| Tipo | Sintaxe | Comportamento |
|------|---------|---------------|
| Unicast | `"to": "w6:p1"` | Entrega a um único agente |
| Broadcast | `"to": "broadcast"` | Entrega a todos os agentes conectados |
| Group | `"to": "group:nome"` | Entrega a membros do grupo nomeado |

### Tipos de mensagem (`MessageType`)

| Tipo | Uso |
|------|-----|
| `task_assign` | Orchestrator → Worker: atribuição de task |
| `task_update` | Worker → Orchestrator: progresso/conclusão |
| `heartbeat` | Watchdog: health check periódico |
| `chat` | Mensagens de texto entre agentes (ACL-controlado) |
| `alert` | Sistema → Orchestrator: alertas de falha/recovery |
| `state_change` | Watchdog → Bus: mudança de estado de agente |

---

## 3. ACL — Controle de Acesso (Quem fala com quem?)

**Arquivo:** [`acl/engine.py`](../src/herdmaster/acl/engine.py) + [`config.toml`](../../config/config.toml)

### Política base

```toml
[acl]
default_policy = "deny"   # TUDO bloqueado por padrão
```

**Regra fundamental:** se não está explicitamente autorizado no `config.toml`, a mensagem é **rejeitada** com `AclDenied`. Não há "permitido por omissão".

### Matriz de Permissões Completa (produção)

| Origem (role) | Destino | can_send_to | can_receive_from | can_dispatch | can_reassign |
|--------------|---------|-------------|------------------|-------------|-------------|
| `orchestrator` | `*` (qualquer) | ✅ | ✅ | ✅ | ✅ |
| `worker` | `orchestrator` | ✅ | ✅ (de orchestrator) | ❌ | ❌ |
| `worker` | `worker` | ❌ **NEGADO** | ❌ **NEGADO** | ❌ | ❌ |
| `peer_reviewer` | `orchestrator` | ✅ | ✅ | ❌ | ❌ |
| `peer_reviewer` | `peer_reviewer` | ✅ | ✅ | ❌ | ❌ |
| `observer` | qualquer | ❌ **NEGADO** | ❌ **NEGADO** | ❌ | ❌ |

### Resposta direta: Agente fala com agente sem autorização do orchestrator?

> **NÃO.** Workers não podem se comunicar diretamente entre si.
> Toda comunicação worker→worker passa necessariamente pelo orchestrator.
> A única exceção é `peer_reviewer ↔ peer_reviewer` — canal explicitamente configurado
> para revisão técnica de pares, controlado pela regra `can_send_to = ["peer_reviewer"]`.

---

## 4. Fluxo de Dispatch de Tasks

**Arquivo:** [`dispatch/injector.py`](../src/herdmaster/dispatch/injector.py)

```
1. Operador/Kiro cria projeto → aprova → tasks entram na queue (state=queued)
2. SquadRecommender seleciona workers (role != orchestrator, health=healthy, state=idle)
3. TaskQueue.claim_next() → task state = assigned
4. DispatchInjector._resolve_pane_id(agent_id) → lê herdr_pane do DB
5. DispatchInjector._wait_idle(pane_id) → aguarda agente idle (até 60s)
6. DispatchInjector._send_prompt(pane_id, prompt) → injeta via Herdr
   ├── Prompt ≤ 4000 chars: keystroke injection em chunks de 700 chars
   └── Prompt > 4000 chars: escreve arquivo .md → envia path para o agente ler
7. Task state = in_progress
8. Worker executa → reporta via herdmaster tasks complete/fail
9. Task state = done/failed
```

### Retries

| Condição | Comportamento |
|---------|--------------|
| Agente não idle (timeout 60s) | Requeue com backoff (1s, 2s, 4s... máx 30s) |
| Herdr error | Retry até max_retries (padrão: 3) |
| max_retries atingido | Task → state=failed (permanente) |

---

## 5. Fluxo de Comunicação Operador → Sistema

O operador (você) e o Kiro são os pontos centrais de comunicação:

```
VOCÊ ─────────────────────────────────────────► KIRO (Orchestrator)
  │  (via Antigravity/CLI em linguagem natural)      │
  │                                                   │ despacha tasks
  │                                                   ▼
  │                                           Workers (AGY, Codex)
  │                                                   │
  │                                                   │ reportam resultado
  │                                                   ▼
  └◄──────────────────────────────────────────── KIRO
       (resultado consolidado / report / evidência)
```

**Em nenhuma hipótese** o operador deve se comunicar diretamente com workers, exceto em casos
de crash de sistema onde o Kiro não está disponível.

---

## 6. Agentes que NÃO precisam de pane Herdr

| Agente | Motivo | Fonte |
|--------|--------|-------|
| `CLI Operator` (cli) | `role=orchestrator` + seed agent de sistema. Nunca executa tasks. | `schema.py:17` (nullable), `squad.py:33` (filtrado) |

Todos os outros agentes com `role=worker` **precisam** de `herdr_pane` configurado para receber tasks.

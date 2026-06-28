# 00 — Visão & Arquitetura

## 1. Visão de produto

A AOP é uma **plataforma SaaS multi-tenant agnóstica de orquestração de agentes de IA**. O cliente aluga acesso (login/senha) e recebe um ambiente onde monta sua própria **squad de agentes**, sempre coordenada por um ou mais **Team Leaders (TL)**.

Diferenciais de produto:

- **Modos de trabalho flexíveis** — o cliente escolhe o que preferir: por **tarefa**, por **squad**, por **projeto** ou por **Kanban**.
- **Execução dual-mode**:
  - **Terminal / multiplexador** (tmux/Herdr "Order") — engine já pronto, copiado do projeto Herdr.
  - **Socket / HTTP** (FastAPI/Python via HerdMaster) — para quem prefere orquestração programática.
- **FinOps granular em tempo real** — breakdown de custo por projeto, tarefa, grupo de TLs, grupo de agentes, Kanban e **por modelo** (OpenAI, Google/Gemini, etc.), incluindo consumo de tokens em tempo real.
- **Observabilidade premium** — KPIs via Prometheus + Grafana e dashboards no frontend.
- **Login de agentes** reaproveitado do **Herdr** (operacional no projeto irmão).

> **Prioridade atual (decisão do produto):** subir toda a plataforma com os componentes **mandatórios** funcionando para **testes com agentes reais** — Kanban, terminais, projetos, tarefas e monitoramento de custos (FinOps). Os módulos de **identidade do cliente (login/senha, tenant, RBAC)** e **aluguel/assinatura (planos, seats, fatura)** são **fase 2/3** e estão fora do escopo imediato. Ver [`90-DECISOES/91-ADRs.md`](90-DECISOES/91-ADRs.md).

---

## 2. Topologia de serviços

```
                 Host (127.0.0.1 — tudo bound em loopback)
 ┌──────────────────────────────────────────────────────────────────┐
 │  Frontend Next.js            :13000   (npm run dev)                 │
 │      │  NEXT_PUBLIC_API_URL → :8090                                 │
 │      ▼                                                              │
 │  AOP Control-Plane (FastAPI/uvicorn)   :8090                        │
 │      │  app.main:app                                                │
 │      │   ├─ HERDMASTER_URL  → :8080 (Bearer token)                  │
 │      │   ├─ DATABASE_URL    → Postgres :5432                        │
 │      │   └─ REDIS_URL       → Redis :6379                           │
 │      ▼                                                              │
 │  HerdMaster (control plane irmão)      :8080  (Bearer token)        │
 │      └─ Herdr socket (AF_UNIX)  ~/.config/herdr/herdr.sock          │
 │                                                                     │
 │  Base (docker compose — deploy/docker-compose.yml):                 │
 │      Postgres  pgvector/pgvector:pg17   :5432                       │
 │      Redis     redis:7-alpine           :6379                       │
 │                                                                     │
 │  Observabilidade (compose em ../HerdMaster/deploy/observability):   │
 │      Prometheus :9090 · Grafana :3000 · Alertmanager :9093          │
 │      Blackbox :9115 · Remediation webhook :9099                     │
 └──────────────────────────────────────────────────────────────────┘
```

**Fonte:** `ops/common.sh` (variáveis de porta e `print_status_table`), `ops/start.sh` (ordem de boot), `deploy/docker-compose.yml` (base).

> **Importante:** **HerdMaster é um projeto IRMÃO da AOP**, não vive dentro dela. O layout esperado é `<ROOT>/AOP` e `<ROOT>/HerdMaster` lado a lado. Em `ops/common.sh`: `ROOT_DIR="$(cd "${AOP_DIR}/.." && pwd)"` e `HERDMASTER_DIR="${ROOT_DIR}/HerdMaster"`.

---

## 3. Mapa de portas (verificado)

| Componente            | Porta | Bind        | Origem da verdade |
|-----------------------|-------|-------------|-------------------|
| Postgres              | 5432  | 127.0.0.1   | `deploy/docker-compose.yml`, `ops/common.sh` |
| Redis                 | 6379  | 127.0.0.1   | `deploy/docker-compose.yml`, `ops/common.sh` |
| HerdMaster API        | 8080  | 127.0.0.1   | `ops/common.sh` (`HERDMASTER_PORT`) |
| AOP Control-Plane API | 8090  | 127.0.0.1   | `ops/common.sh` (`AOP_API_PORT`) |
| AOP Frontend (web)    | 13000 | 127.0.0.1   | `ops/common.sh` (`AOP_WEB_PORT`) |
| Prometheus            | 9090  | 127.0.0.1   | `ops/common.sh` (`print_status_table`) |
| Grafana               | 3000  | 127.0.0.1   | `ops/common.sh` (`print_status_table`) |
| Alertmanager          | 9093  | 127.0.0.1   | `ops/common.sh` (`print_status_table`) |
| Blackbox exporter     | 9115  | 127.0.0.1   | `ops/common.sh` (`print_status_table`) |
| Remediation webhook   | 9099  | 127.0.0.1   | `ops/common.sh` (`print_status_table`) |

### Verificação (executar quando o stack estiver de pé)

```bash
# Mostra a tabela de status oficial com todas as portas e healthchecks
bash AOP/ops/start.sh   # ao final imprime print_status_table
# ou, sem subir nada, apenas portas em escuta:
ss -ltn | grep -E ':(5432|6379|8080|8090|13000|9090|3000|9093|9115|9099)\b'
```

---

## 4. Estado real x pretendido (honestidade de status)

| Capacidade                                   | Pretendido (visão)                                  | Estado real no código                                                                 | Doc |
|----------------------------------------------|-----------------------------------------------------|----------------------------------------------------------------------------------------|-----|
| Base Postgres + Redis                        | persistência multi-tenant                           | ✅ compose funcional (redis **sem** `requirepass`)                                     | 15  |
| Control-plane FastAPI                        | API completa de orquestração                        | ✅ endpoints existem (tasks, squads, agents, finops, tracing)                          | 31  |
| Frontend                                     | dashboards + Kanban + squad builder                 | ✅ rotas existem (`/finops`, `/projects`, `/squad-builder`, ...)                       | 32  |
| Execução terminal-mode                       | rastrear tarefa até conclusão real                  | ⚠️ **stub**: lê estado **uma vez** e declara `DONE`; `meter()` usa `seat_seconds=0`    | 34  |
| Execução socket-mode                         | polling até estado terminal                         | ⚠️ **stub**: `max_polls=1` por padrão → declara `DONE` após 1 poll                     | 34  |
| FinOps alimentado automaticamente            | executores gravam custo em tempo real               | ❌ **gap**: custo só entra via `POST /finops/costs/*` manual; executores não alimentam | 34, 35 |
| Custo por modelo / Kanban / grupo de TL      | breakdown granular                                  | ⚠️ rollup agrupa **só** por tenant/projeto e token-vs-seat; `model` só em metadata     | 35  |
| Identidade do cliente (login/senha/RBAC)     | obrigatório no produto final                        | ❌ **inexistente** (fase 2/3)                                                          | 91  |
| Aluguel/assinatura (planos/seats/fatura)     | obrigatório no produto final                        | ❌ **inexistente** (fase 2/3)                                                          | 91  |

> Detalhes e evidências de cada linha estão nos documentos referenciados na coluna **Doc**.

---

## 5. Glossário

- **TL (Team Leader / orchestrator):** agente com permissão de despachar/reatribuir tarefas. No ACL do HerdMaster o papel `orchestrator` (agente `cli`) pode enviar/receber para `*`.
- **Worker:** agente executor; no ACL só fala com o `cli` (TL). Comunicação lateral worker↔worker é **negada por padrão** (`default_policy = deny`).
- **Dual-mode:** `OperationMode.TERMINAL` (Herdr) e `OperationMode.SOCKET` (HerdMaster HTTP).
- **Coupling:** camada que escolhe adaptadores reais Herdr/HerdMaster com **degradação graciosa** quando indisponíveis (ADR-001).
- **FinOps engine:** cálculo dual de custo — **token** (pay-as-you-go) e **seat** (utilização de assinatura).

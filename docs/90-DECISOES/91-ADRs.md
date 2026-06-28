# 91 — Decisões Arquiteturais (ADRs)

Registro de decisões. Formato: contexto → decisão → status → consequências. Decisões **irreversíveis** (ou caras de reverter) marcadas como tal.

---

## ADR-001 — Acoplamento com degradação graciosa Herdr/HerdMaster
- **Contexto:** a AOP não reimplementa orquestração de baixo nível; reusa Herdr (terminal) e HerdMaster (socket/HTTP).
- **Decisão:** `build_coupled_executors` escolhe adaptadores reais quando disponíveis e cai em fallback quando não, marcando `CouplingPhase.DEGRADED`. Sem token, o coupling fica `degraded` mas o sistema continua de pé.
- **Status:** ✅ implementado (`coupling/wiring.py`, `app/main.py::_coupling_health`).
- **Consequências:** robustez para testar partes isoladas; porém "verde" no smoke pode mascarar que o socket usou fallback (doc 41).

## ADR-002 — Stack base mínimo no Compose; apps como processos de host
- **Contexto:** equilíbrio entre simplicidade e controle.
- **Decisão:** `docker-compose.yml` sobe **só** Postgres+Redis. HerdMaster, control-plane e frontend rodam como processos de host via `start.sh` (PID files em `/tmp/aop-ops-run`). Observabilidade vive em compose separado no HerdMaster irmão.
- **Status:** ✅ implementado.
- **Consequências:** boot orquestrado por shell idempotente; menos isolamento que containerizar tudo. Reavaliar para produção (containerizar control-plane/web).

## ADR-003 — Postgres com pgvector
- **Contexto:** futuras features de memória/RAG.
- **Decisão:** imagem `pgvector/pgvector:pg17`.
- **Status:** ✅ implementado. **Irreversível na prática** (dados/extensão).
- **Consequências:** embeddings disponíveis sem trocar de banco.

## ADR-004 — Design System Indra v3.0, HEX obrigatório
- **Contexto:** consistência visual premium.
- **Decisão:** tokens **somente hexadecimais**; **proibido OKLCH**; fonte canônica `web/src/app/globals.css`.
- **Status:** ✅ vigente. **Regra dura.**
- **Consequências:** qualquer cor fora da paleta/OKLCH é violação (ver doc 32 verificação).

## ADR-005 — Identidade e billing são fase 2/3
- **Contexto:** prioridade do produto é subir o core operacional para testar com agentes reais.
- **Decisão:** **adiar** login/senha/tenant/RBAC e planos/seats/fatura. Focar Kanban, terminais, projetos, tarefas, FinOps.
- **Status:** ✅ decisão de produto vigente.
- **Consequências:** a plataforma roda sem auth de cliente hoje (gap conhecido). **Não expor à internet** sem essa camada (bind `127.0.0.1` mitiga no curto prazo).

## ADR-006 — FinOps dual-engine (token + seat)
- **Contexto:** clientes pay-as-you-go e por assinatura.
- **Decisão:** dois motores de custo (`CostEngine.TOKEN` e `SEAT`) com atribuição hierárquica tenant→project→issue→agent→runtime.
- **Status:** ✅ base implementada; ⚠️ agregações multidimensionais e alimentação automática pendentes (doc 35).
- **Consequências:** fundação correta; falta granularidade (modelo/Kanban/grupo) e automação.

## ADR-007 — ACL default-deny para topologia de squad
- **Contexto:** evitar comunicação lateral não autorizada entre agentes.
- **Decisão:** `default_policy = "deny"`; `orchestrator` fala com `*`, `worker` só com `cli`. Aplicado no TOML do HerdMaster e refletido na governança humana da squad.
- **Status:** ✅ implementado e provado (smoke E2E, doc 41).
- **Consequências:** segurança por padrão; engenheiros coordenam via TL (doc 51).

## ADR-008 — Governança de squad com ledger obrigatório
- **Contexto:** 8 agentes em paralelo, risco de colisão e token-burn.
- **Decisão:** ondas com escopo disjunto + git worktrees + ledger append-only de check-in/out com evidência + merge centralizado no TL + monitoramento ~90s.
- **Status:** ✅ definido (docs 51–54, ledger em `CHECKIN_OUT.md`).
- **Consequências:** rastreabilidade e anticolisão; overhead de coordenação assumido como necessário.

## ADR-009 — Rotação automática de contas por esgotamento de token (janela 5h)
- **Contexto:** agentes têm limite de tokens a cada ~5h; ao esgotar, o vendor para o agente e exige trocar de conta. Operamos com **múltiplas assinaturas/contas**.
- **Decisão:** modelar cada **conta como um `Seat`** (isolamento de credenciais por `home_dir`/`config_dir`) e implementar **rotação automática**: detectar esgotamento (proativo via ledger de quota + reativo via padrão/429), deslogar a conta exausta, logar na próxima conta disponível (via `DeviceLoginService`), restaurar o runtime e **retomar a tarefa**. Reaproveitar `SeatPool`, `DeviceLoginService` e `QuotaAwareScheduler`/`QuotaLedger`. **Preferir device-login (OAuth)** a senha em disco.
- **Status:** 🟢 **esqueleto implementado e testado** (`control-plane/rotation/`, 19 testes) + wiring opcional no `AppState` (`AOP_ROTATION_ENABLED`, default false). Faltam pontos de extensão de runtime (resume hook + gatilho de detecção no dispatch) para "100% no ar" — doc 36 §11.
- **Consequências:** elimina a parada manual por esgotamento; exige gestão segura de credenciais e tratamento de perda de contexto no logout; custo passa a ser atribuível **por conta**.

---

## Decisões em aberto (a decidir pela squad/TL)

| ID | Questão | Opções | Recomendação |
|----|---------|--------|--------------|
| OPEN-1 | Gateway de LLM para custo/budget automático | LiteLLM proxy vs instrumentação direta | avaliar LiteLLM (doc 92) |
| OPEN-2 | Padrão de telemetria de custo | OTel GenAI semconv vs schema próprio | adotar OTel GenAI (doc 92) |
| OPEN-3 | Formato de dados de billing | FOCUS (FinOps Foundation) vs ad-hoc | mapear rollups para FOCUS (doc 92) |
| OPEN-4 | Isolamento de runtime para 8 agentes | worktrees + 1 stack vs N stacks/containers | worktrees + stack único pelo TL (doc 52) |
| OPEN-5 | Containerizar control-plane/web | sim vs manter host process | sim para produção (revisar ADR-002) |

---

## Dívidas técnicas registradas (correções da Onda 0)

Itens descobertos durante a documentação, verificados contra o código:

1. **`smoke_e2e.py` asserta `/health == {"status":"ok"}`** mas o código atual retorna `+coupling` → asserção falha contra o código atual (doc 41 §3).
2. **`db-backup.sh` `BACKUP_ROOT` default obsoleto** (`/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/...`) (doc 22 §2).
3. **`install-backup-cron.sh` não exporta `BACKUP_ROOT`** → cron herda o default obsoleto (doc 25).
4. **`status360.py`/`run-dashboard.sh` com paths hardcoded obsoletos** + SCOPE da squad antiga (doc 25 §1).
5. **Redis sem `requirepass`** apesar de `REDIS_PASSWORD` no `.env` (doc 13 §1).
6. **`/metrics` FinOps hardcoded** em `tenant-a`/`project-a` (doc 23 §2, doc 35 §4).
7. **Executores não alimentam FinOps** + rastreamento stub (`max_polls=1`, `read_state` único) (doc 34).

> Estas dívidas são o escopo natural da **Onda 0** (doc 52 §4), de baixo risco e alta paralelização.

OK# 🎯 MASTER DELIVERY PLAN — AOP (Agnostic Orchestration Platform)
**Para:** Tech-Lead / Orchestrator — **KIRO_OPUS-48**
**De:** Suporte de Engenharia (Herdr Ops + consolidação de planejamento)
**Data:** 2026-06-27 · **Projeto:** AOP — gerido como PROD
**Metodologia mandatória:** GSD (`Discuss → Plan → Execute → Verify → Ship`) — sem skip (ref. `GSD_MANDATORY_PROTOCOL.md`)

> **Propósito.** Este é o plano-mestre único para LEVAR A AOP A 100%. Consolida, numa só fonte:
> (1) o que já foi entregue e verificado, (2) o que falta — derivado *exatamente* das fontes
> (`openspec/changes/agnostic-orchestration-platform/tasks.md`, `FINAL_STATUS_REPORT_TL.md`,
> `TECH_DEBT_BACKLOG.md`, `ROADMAP.md`, PRD-003, PRD-004), e (3) a sequência de ondas com donos,
> ETA e regra de evidência. **Nada aqui é inventado** — cada item cita sua fonte.
>
> **Regra de evidência inegociável (do TL_HANDOFF):** CHECK-IN antes de iniciar + CHECK-OUT com
> `timestamp + nome do agente + PRINT real` em `CHECKIN_OUT_GSD.md` (raiz). Sem print = task inválida.

---

## 0. Veredito de baseline (TL-verificado, fonte: FINAL_STATUS_REPORT_TL.md)
- App **compila** (`npm run build` EXIT=0, 14 rotas) e **sobe** (HerdMaster :8080, AOP API :8090, front :13000 = 200).
- Design System **Indra HEX** verificado (0 OKLCH / 66 HEX, 15 componentes ui).
- Coupling control-plane↔HerdMaster **connected**.
- **NÃO está 100%.** Pendências reais consolidadas abaixo.
- **OpenSpec `agnostic-orchestration-platform`: 51/65 (14 abertos)** — `openspec list` confirma.

---

## 1. Inventário de entrega (delivered vs pendente) — fonte única

### 1A. Fases de produto F0–F7 (ROADMAP.md + STATUS.md + FINAL_STATUS_REPORT_TL.md)
| Fase | Escopo | Dono | Status verificado | Pendência exata |
|---|---|---|---|---|
| F0 | Design System Indra HEX + Shell (menu lateral) | AG-1 | ✅ VERIFIED (build, hex=66/oklch=0, ui=15) | Verify/Ship formal pendente |
| F1 | Projects (backend+UI) | AG-2 | ✅ VERIFIED | Ship formal |
| F2 | Issues/Tasks **Kanban** + dual-mode (terminal/socket) | AG-2 | 🟡 MOCK RESIDUAL | **TD13**: `issues-view.tsx:629` progress HARDCODED; print real (Playwright) |
| F3 | Squad Builder v2 + Agents (papel por nó, excluir nó) | AG-3 | ✅ VERIFIED (rotas topology) | Closeout + 8.4 chatbot (diferível) |
| F4 | Seats + Sessions/OAuth Device-Login | AG-4 | ✅ VERIFIED | Ship formal |
| F5 | FinOps + Observability + Live | AG-5 | 🟡 STRINGS FIXAS | **TD13**: `observability:92` summary hardcoded |
| F6 | Settings + Inbox + My-Issues + Search (Cmd+K) | AG-6 | ✅ VERIFIED | Ship formal |
| F7 | E2E + UI Review (6 pilares) + Perf/A11y | rotativo | ⬜ PENDENTE | Roda por último (TD10) |

### 1B. As 14 tasks OpenSpec abertas (fonte: tasks.md `agnostic-orchestration-platform`)
| # | Task | Capability | Bloqueia GA? |
|---|---|---|---|
| 1.3a | Migração HerdMaster SQLite→**Postgres unificado** (D11) | persistence | **SIM (P0)** — lock pain documentado |
| 3.2 | Adapters nativos por vendor (codex/kiro/antigravity/gemini) c/ estado semântico (o **moat**) | agent-runtime-adapter | SIM (P1) |
| 3.3 | Fallback de detecção por screen-scrape | agent-runtime-adapter | P2 |
| 8.4 | Chatbot opcional que propõe squad+topologia | visual-squad-builder | NÃO (diferível, liga em D16/Fase 3) |
| 10.1 | Isolamento multi-tenant de recursos | multi-tenant-identity | SIM (P1) |
| 10.3 | RBAC (admin/operator/viewer) + auditoria | multi-tenant-identity | SIM (P1) |
| 11.4 | Audit log imutável (lease/topologia/autonomia/billing) | observability-tracing | SIM (P1) |
| 13.2 | Confirmar ToS de concorrência por seat (OpenAI/Google) | validation | **SIM (P0 pré-GA, não-código)** |
| 13.3 | Teste de carga local (~10 agentes-pai, fan-out 2–3) | validation | SIM (P1) |
| 15.1 | Isolamento worktree/path-guard | parallel-execution-governance | SIM (P1) |
| 15.2 | Ledger de check-in/out em disco (append-only) | parallel-execution-governance | SIM (P1) |
| 15.3 | Flag de violação por check-out ausente (timeout) | parallel-execution-governance | P2 |
| 15.4 | Validação de evidência obrigatória em toda entrega | parallel-execution-governance | SIM (P1) |
| 15.5 | Vincular evidência+ledger ao `trace_id` | parallel-execution-governance | P2 |

> Observação de reconciliação: `tasks.md` item 12.1 ainda diz "OKLCH" mas o app migrou para
> **Indra HEX**. Atualizar o texto do spec p/ refletir realidade (item de doc, não de código).

### 1C. Tech-debt aberto (fonte: TECH_DEBT_BACKLOG.md + FINAL_STATUS_REPORT_TL.md TD12–TD14)
| ID | Débito | Prio | Fonte |
|---|---|---|---|
| **TD12** | DB: consolidar 33 schemas; mover `tasks/task_audit_log/task_alerts` de `hm_test_*` p/ schema canônico; limpar `ag*_*`/`*_evidence` | **P0** | TL §3.3 |
| TD8 | Reconciliar OpenSpec ↔ código (14 abertos) — manter `tasks.md` fiel à realidade | P1 | TL §1 |
| TD13 | Remover mock residual (`issues-view.tsx:629`, `observability:92`) | P1 | TL §3.1/§3.4 |
| TD14 | Prometheus 2 targets DOWN (`herdmaster-internal-metrics`, `herdmaster-remediation`) | P1 | TL §3.4 |
| TD7 | Grafana: publicar porta + dashboards por agente/rota | P2 | BACKLOG_GRAFANA GRAF-06/07 |
| TD9 | Integração F1→F6 ponta-a-ponta (smoke) | P2 | TL §1 |
| TD10 | QA E2E exaustivo (= F7) | P3 | regra |

### 1D. Change nova NÃO construída (fonte: `agent-route-dashboards-provisioning/tasks.md`)
- **0/25 tasks.** Backend dashboards/provisioning + API + frontend + testes em `AOP/control-plane/` e `AOP/web/`. Validado no OpenSpec, **implementação não iniciada** (verificado: módulos inexistentes).

### 1E. Backlog diferido (fonte: design.md "Backlog / Diferidos")
- `psycopg[binary]` pin em `HerdMaster/pyproject.toml` (1 linha; reprodutibilidade).
- `npm audit` 2 vulnerabilidades moderadas em `AOP/web`.
- Executors usam `InMemoryQueueClient`/`LocalRuntimeAdapter` → trocar por HerdrAdapter real + fila HerdMaster.
- Topology persistence in-memory → Postgres.
- Endpoint live `send_message`/`handoff` p/ enforcement de ACL em runtime.
- Cliente HerdMaster tokenizado (bearer :8080).
- **Fase 3 (diferida por decisão, D16):** NLP/ChatOps (`herdmaster ask` / chatbot do builder = 8.4).

---

## 2. Sequência de execução (ondas) — caminho crítico para ZERAR
> Princípio (TECH_DEBT_BACKLOG): agentes 24×7, acabou um → puxa o próximo ⬜, até zerar.
> Cada item percorre o GSD e fecha com CHECK-OUT + PRINT no ledger raiz.

### ONDA A — Fundação crítica (P0, desbloqueia tudo)
| Item | O quê | Dono sugerido | ETA |
|---|---|---|---|
| 1.3a + TD12 | Migração/consolidação Postgres unificado: mover tasks/audit de `hm_test_*` p/ schema canônico; limpar poluição; eliminar lock single-writer | 1 agente backend dedicado | 60–90m |
| TD14 | Religar 2 targets Prometheus DOWN (pré-requisito de observabilidade real) | 1 agente infra | 30m |
| 13.2 | Confirmar ToS de concorrência por seat (OpenAI/Google) — **não-código, decisão de negócio** | TL/stakeholder | assíncrono |

### ONDA B — Integridade de produto (P1, em paralelo após A)
| Item | O quê | Dono | ETA |
|---|---|---|---|
| TD13 | Remover mock residual (issues progress, observability summary) → zero-mock real | AG-2 / AG-5 | 30m |
| 10.1 + 10.3 | Isolamento multi-tenant + RBAC (admin/operator/viewer) + auditoria | backend auth | 120m |
| 11.4 | Audit log imutável (lease/topologia/autonomia/billing) | backend obs | 90m |
| 15.1–15.5 | Governança de execução paralela (worktree/path-guard, ledger em disco, timeout flag, evidência obrigatória, trace_id) | backend gov | 120m |
| 3.2 | Adapters nativos por vendor c/ estado semântico (**o moat** — reaproveitar os manifests Herdr já validados, ver Annex) | backend adapter | 120m |
| TD8 | Reconciliar `tasks.md` ↔ código a cada fechamento (incl. corrigir texto 12.1 OKLCH→HEX) | TL/rotativo | contínuo |

### ONDA C — Cobertura e dashboards (P2)
| Item | O quê | Dono | ETA |
|---|---|---|---|
| 3.3 | Fallback screen-scrape (reusa exatamente a técnica de manifest/`agent explain` do Annex) | backend adapter | 60m |
| TD7 | Grafana dashboards por agente/rota + porta publicada (PRD-003 as-code) | infra | 60m |
| `agent-route-dashboards-provisioning` (25 tasks) | Dashboards+provisioning backend/API/frontend/testes | squad (5 seções) | 1–2 ondas |
| 8.4 / Fase 3 | Chatbot squad-proposer / NLP — **diferível** (D16) | — | Fase 3 |

### ONDA D — Fechamento (P3)
| Item | O quê | Dono | ETA |
|---|---|---|---|
| 13.3 | Teste de carga local (~10 agentes-pai, fan-out 2–3, i9/64GB) | QA | 60m |
| TD9 | Smoke integração F1→F6 | QA | 60m |
| F7 / TD10 | E2E exaustivo + UI Review (6 pilares) + Perf/A11y + Ship de todas as fases | rotativo | final |

---

## 3. Gate de GSD por item (o TL faz cumprir)
Nenhum item avança sem: **artefato da etapa** (`phases/<f>/{RESEARCH,DISCUSS,PLAN,VERIFY}.md`) +
**build/pytest verdes** + **dados reais (zero mock)** + **PRINT real** anexado +
**CHECK-OUT** no ledger raiz. F7 só abre após Ondas A–C fechadas.

## 4. Critério de "AOP 100%"
1. 65/65 OpenSpec done (`openspec validate --strict` limpo) e change arquivada.
2. 0 mock/placeholder em produção (grep limpo nos pontos de TD13).
3. Postgres consolidado (sem `hm_test_*`/poluição), 0 `database is locked`.
4. Prometheus 100% targets UP; Grafana dashboards as-code por agente/rota.
5. F0–F7 com Ship + PRINT no ledger; E2E verde; UI-review 6 pilares ok.
6. ToS de seat confirmado (13.2) antes de GA.

## 5. Papéis
- **TL (KIRO_OPUS-48):** orquestra ondas, valida check-outs com print, mantém `STATUS.md`/`tasks.md` fiéis, decide GA.
- **Suporte Herdr Ops (este autor):** fornece a base operacional de como o Herdr se comporta no dia-a-dia (detecção de estado, dispatch, agents-flush, waits, reset por harness) — ver `HERDR_OPS_SUPPORT_ANNEX_TL.md`. Esse conhecimento alimenta diretamente as tasks 3.2/3.3 (adapters/estado) e a operação de despacho das ondas.

## 6. Fontes (rastreabilidade — tudo verificado, nada inventado)
`openspec/changes/agnostic-orchestration-platform/{tasks.md,design.md,proposal.md}` ·
`openspec/changes/agent-route-dashboards-provisioning/tasks.md` ·
`AOP/.planning/{PROJECT.md,ROADMAP.md,STATUS.md,TECH_DEBT_BACKLOG.md,TL_HANDOFF.md,FINAL_STATUS_REPORT_TL.md,OPENSPEC_RECONCILIATION.md}` ·
`AgnosticAI_Platform/docs/PRD_FEATURE_REQ_004.md` · `HerdMaster/docs/feature_003_dashboard_expansion/PRD_FEATURE_REQ_003.md` ·
`AOP/docs/BACKLOG_GRAFANA.md` · `openspec list/validate` (CLI v1.4.1).

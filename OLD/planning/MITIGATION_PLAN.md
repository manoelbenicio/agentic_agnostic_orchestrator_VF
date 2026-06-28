# PLANO DE MITIGAÇÃO & RESOLUÇÃO — AOP (governança séria)
Autor: Kiro (planner/arquiteto). Cada cenário que deu errado tem detecção + mitigação + dono.

## A. Matriz de falhas que OCORRERAM → mitigação
| # | Falha que aconteceu | Impacto | Mitigação / Resolução | Estado |
|---|---|---|---|---|
| 1 | Postgres com transação envenenada (FK sem CASCADE) | dispatch loop morto, **0 agentes** | FK `ON DELETE CASCADE` (Codex P0) + reconnect/rollback automático na conexão | ✅ corrigido |
| 2 | Sprawl de 557 schemas `hm_*` por boot | lixo/lock exhaustion | schema único `hm_main` + cleanup de órfãos no boot | ✅ corrigido |
| 3 | Flush no store errado (sqlite, sendo Postgres) | ação perdida | documentado: store=Postgres; `reset-hard` mira Postgres | ✅ documentado |
| 4 | `herdr send-text` não dava Enter → TL não agia | dispatch silenciosamente parado | **sempre `pane run`** (texto+Enter) + ler o pane após p/ confirmar submissão | ✅ regra ativa |
| 5 | Agente foi idle no meio da task (AG-1) | task parada sem aviso | reconciliador detecta `in_progress`+idle → nudge/realoca | ⏳ OTTL |
| 6 | Agente crashou (Nemotron) → task órfã, status incerto | **crítico/amador** | **PROCEDIMENTO DE CRASH** (abaixo) | ✅ codificado |
| 7 | `tasks=0` no Postgres (TL injeta no pane, não cria task) | **sem trilha/auditoria, não dá p/ pesquisar** | **OTTL**: `tasks create` obrigatório no dispatch → popula `tasks`+`task_audit_log` | ⏳ a distribuir |
| 8 | QA E2E rodado cedo demais | ciclos desperdiçados | **QA E2E só no FINAL** (F7), após todos fixes+features | ✅ regra ativa |
| 9 | Entregas sem evidência ("vendidos sem controle") | risco de fake-done | check-out **obrigatório com PRINT+SHA256**; reconciliador marca `INVALID_COMPLETION` | ✅ enforce (auditado) |
| 10 | Trabalho perdido (varredura de telas vazias não salva) | conhecimento sumiu | **toda varredura/auditoria vira artefato em disco**, nunca só no chat | ✅ regra ativa |

## B. PROCEDIMENTO DE CRASH (reforçado — imediato, sem gap de status)
Agente caiu durante execução:
1. TL detecta (heartbeat morto / pane sumiu) → **realoca IMEDIATAMENTE** a outro worker. Sem "status incerto".
2. Novo worker: ou **refaz do zero**, ou **investiga onde parou** (retomada idempotente) — decisão do TL pela natureza da task.
3. **Sempre exigir EVIDÊNCIA** da entrega (PRINT+SHA+testes) no check-out.
4. Substituir agente morto no roster na hora. Handoff registrado no ledger.

## C. ORDEM correta (QA por último)
Fixes → Features (todas as frentes) → Integração F1→F6 → **QA E2E exaustivo (F7) UMA vez** → Ship.

## D. Estado real auditado (disco + Postgres) — 26/06 ~15:30 UTC
- **Ledger**: 16 check-in / 11 check-out; **11/11 check-outs COM evidência (PRINT+SHA256)** ✅; 5 check-ins abertos (em curso/ a reconciliar).
- **Postgres hm_main**: tabelas existem (`tasks`, `task_audit_log`, `agents`, `health_events`, `messages`, `projects`...), **MAS `tasks=0`** → trilha de injeção NÃO está sendo gravada (gap → OTTL). `agents=12` (entradas stale de reconexões), `health_events=619`.
- **Observability**: prometheus + grafana + alertmanager **UP** (containers), porém **dashboards/scrape customizados por agente/componente + monitor E2E de API = PENDENTE** (deep dive não feito).
- **Telas (rotas existem)**: finops, inbox, issues(=Kanban), live, my-issues, observability, projects, seats, sessions, settings, squad-builder. AG-1..6 entregaram a maioria; **squad-builder (AG-3) em andamento**.
- **Varredura de telas vazias**: **NÃO há artefato em disco** — aquele levantamento se perdeu (feito em sessão anterior, nunca salvo). Precisa ser **refeito e salvo** como artefato.

# RELATÓRIO PROFISSIONAL + PLANO DE REMEDIAÇÃO — AOP
Autor: Kiro (Principal Architect). Fundamentado em auditoria de disco/DB (26/06).
Princípio: eu (arquiteto) desenho TUDO (componentes, processos, arquitetura, observabilidade);
workers implementam via TL. Nada de empurrar arquitetura pra worker.

## 1. O QUE FOI MAL FEITO (gaps reais, com evidência)
| # | Gap | Evidência (medida) | Severidade |
|---|-----|--------------------|-----------|
| G1 | Desconexão OpenSpec ↔ realidade | change `agnostic-orchestration-platform` = **2/65 tasks**; código feito fora do backlog | 🔴 alta |
| G2 | Telas rasas vs check-out (overclaim) | `inbox` view 86 ln, `my-issues` 84, `settings` 149 — vs "10 abas/filtros/bulk/4 escopos" declarados | 🔴 alta |
| G3 | Backends ausentes | sem API dedicada p/ `settings`, `inbox`, `squad-builder` (squad Canvas 315ln sem backend) | 🟡 média |
| G4 | Sem trilha de tasks no Postgres | `hm_main.tasks=0`, `task_audit_log=0` — TL injeta no pane, não cria task | 🔴 alta |
| G5 | Observabilidade existe mas RASA por agente | CORRIGIDO c/ dado real: Prometheus tem jobs (`herdmaster-internal-metrics:8080`,`aop-control-plane-metrics:8090`,`herdmaster-e2e-api-monitor`), Grafana tem `aop_finops_tracing.json`+`herdmaster_main.json`. Gap = **EXPANDIR** por agente/rota, não criar do zero | 🟡 média |
| G6 | Varredura de telas vazias perdida | nenhum artefato em disco | 🟡 média |
| G7 | Buracos de processo | send-text sem Enter; crash órfão; QA prematuro; evidência (mitigados em MITIGATION_PLAN.md) | 🟢 mitigado |

## 2. PLANO SÓLIDO DE REMEDIAÇÃO (fases, ordem correta, ASAP)
```
R0 CONTROLE     → OTTL: tasks no Postgres (create obrigatório) + reconciliador + board %/ETA.
   (1º de tudo)   Sem isto continuamos cegos. [dono impl: 1 worker | arq: Kiro]
R1 RECONCILIAR  → mapear CADA tela+backend vs as 65 tasks OpenSpec; marcar real-done x raso;
   A REALIDADE     persistir EMPTY_SCREENS_AUDIT.md. Atualizar tasks.md com o que falta.
R2 PROFUNDIDADE → inbox, my-issues, settings ao nível declarado; backends settings/inbox;
   DE FEATURE      backend do squad-builder. Zero mock, dados reais.
R3 OBSERVABILIDADE→ Grafana dashboards por agente/componente + scrape Prometheus + alertas
   (DEEP DIVE)      + monitor E2E de API (latência/erros por rota). Kanban (/issues) ligado ao OTTL.
R4 INTEGRAÇÃO   → app-shell ligando todas as rotas, consumo ponta-a-ponta real, sem conflito de escopo.
R5 QA E2E       → suíte exaustiva UMA vez (F7). Depois: Ship.
```

## 3. ARQUITETURA POR CASO (resumo; detalhar em specs/)
- **OTTL (R0):** fonte única = `hm_main.tasks` (estado) + `task_audit_log` (trilha imutável: who/what/when/ETA).
  Reconciliador cruza tasks×agents×pane; board CLI + `/observability`.
- **Backends ausentes (R2/R3):** `settings_api` (preferências/tenant), `inbox_api` (eventos/notif), `squad_api`
  (topologia do squad/canvas) — padrão router+repository+schema+tests como os existentes.
- **Observabilidade (R3):** Prometheus scrape de control-plane + HerdMaster + agentes; Grafana com dashboards
  por agente (tokens/custo/latência) e por componente (rota/erro/p95); Alertmanager regras; monitor sintético E2E.

## 4. GOVERNANÇA DESTE PLANO
- Cada fase vira tasks no OpenSpec (`agnostic-orchestration-platform`) + task no HerdMaster (trilha).
- Eu desenho/atualizo specs+design; TL distribui; workers implementam; check-out com PRINT+SHA; crash procedure.
- QA exaustivo só no fim. Nada de testar 100x.

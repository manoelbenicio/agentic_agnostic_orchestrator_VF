# ROADMAP — AOP (Agnostic Orchestration Platform) · Replanejamento GSD

> **Metodologia:** GSD (Discuss → Plan → Execute → Verify → Ship), uma fase por vez, **nenhuma pulada**.
> **Design System:** Indra DSS v3.0 — **HEXADECIMAL mandatório** (sem OKLCH). Tokens já aplicados em `AOP/web/src/app/globals.css`.
> **Governança:** 100% agêntica, 6 agentes, paths isolados, check-in/out na **raiz** (`CHECKIN_OUT_GSD.md`), evidência obrigatória, **zero mock/placeholder em produção**.
> **Visão de produto:** web app disruptivo, alto nível visual (efeitos/micro-interações), **menu lateral esquerdo**, experiência premium nível Fortune 500.

## Paleta Indra (HEX) — referência obrigatória
deep `#002B3A` · dark `#003E50` · primary `#06596E` · secondary `#346679` · **cyan `#00B0BD` (accent)** · teal `#3F96AE` · light `#7A9CAE` · blue-gray `#B3C1DA` · sky `#BADFF3` · warm `#B0B4BD` · off `#E8E8E1` · off-white `#F2F5F6` · white `#FFFFFF` · ink `#00475A` · gray `#65655F` · line `#C7CBC5` · success `#27AE60` · warning `#FF9800` · error `#E91E63` · gold `#FFC107`

## Skills aplicadas
- **Web visual/UX:** princípios de `visual-kpi-designer` (componentes KPI/gauges/status), `executive-status-storyteller` (tom McKinsey/headlines), `slide-animation-director` → portados p/ web via `css-animation-microinteraction-expert`; `fortune500-executive-dashboard`, `senior-uiux-data-products`, `shadcn`, `tailwindcss-advanced-layouts`.
- **Terminal/infra (kanban↔terminal):** `linux-shell-scripting`, `linux-troubleshooting`, `bash-linux`, `linux-privilege-escalation`.
- **Workflow:** `gsd-spec-phase`, `gsd-plan-phase`, `gsd-execute-phase`, `gsd-ui-review`, `gsd-add-phase`, `gsd-sketch`.

## Ciclo obrigatório por fase (SEM SKIP)
Cada fase F0–F7 percorre o ciclo GSD COMPLETO, na ordem, sem pular nenhuma etapa — e cada
etapa gera artefato documentado + CHECK-IN/CHECK-OUT com **print real** no ledger raiz:

| Etapa | Comando GSD | Artefato | "Feito" quando |
|---|---|---|---|
| 1. Research | `/gsd-research-phase <n>` | `phases/<fase>/RESEARCH.md` | fontes/decisões técnicas levantadas |
| 2. Discuss | `/gsd-discuss-phase <n>` | `phases/<fase>/DISCUSS.md` | requisitos clarificados (ambiguity score baixo) |
| 3. Plan | `/gsd-plan-phase <n>` | `phases/<fase>/PLAN.md` | plano com verificação aprovado |
| 4. Execute | `/gsd-execute-phase <n>` | código + evidência | build/pytest verdes, sem mock, PRINT real |
| 5. Verify | `/gsd-verify-work` + `/gsd-ui-review` | `phases/<fase>/VERIFY.md` | UAT + UI-review (6 pilares) ok |
| 6. Ship | `/gsd-ship` | PR/registro | mesclado/registrado com evidência |

REGRA: não avançar de etapa nem de fase sem o artefato + check-out com print. SPEC.md de cada
fase (F0–F7) já existe como base do passo Spec/Discuss.

## Fases (todas documentadas)

### FASE 0 — Design System Indra HEX + Shell (menu lateral + efeitos) · Dono: AG-1
- **Spec:** biblioteca de componentes (Button/Input/Select/Dialog/Dropdown/Tabs/Table/Card/Badge/Toast/Tooltip/Skeleton/EmptyState/Avatar) em HEX Indra; **menu lateral esquerdo** agrupado; header com busca/tema/status; micro-interações (fade/float/wipe "invisíveis"); light/dark.
- **Aceite:** todos os componentes usando tokens HEX; shell responsivo alinhado; `npm run build` verde; screenshot.

### FASE 1 — Projects (UI + backend) · Dono: AG-2
- **Spec:** tabela `projects` + endpoints CRUD; tela lista+board; criar/editar/excluir; progresso real.
- **Aceite:** CRUD real (curls), tela consumindo API, sem dado fake; pytest+build verdes.

### FASE 2 — Issues/Tasks (tracker + criar + despachar + detalhe live) · Dono: AG-2
- **Spec:** kanban (Backlog→Done) + List/Swimlane/Gantt; modal criar com **modo terminal/socket**; detalhe com timeline + painel live (WS) + execution logs; bulk actions.
- **Aceite:** criar+despachar nos 2 modos; ciclo de vida real; pytest+build verdes.

### FASE 3 — Squad Builder v2 + Agents · Dono: AG-3
- **Spec:** canvas com paleta+contagem; **papel por nó (worker↔Tech-Lead)**; **excluir nó** in-canvas; salvar/validar topologia→ACL; tela Agents (registry CRUD).
- **Aceite:** ops de nó funcionando; topologia vira ACL real; pytest+build verdes.

### FASE 4 — Seats + Sessions/OAuth · Dono: AG-4
- **Spec:** endpoints de provisionamento de seats (fim do hardcoded); tela Seats; device-login por vendor (Codex/Claude/Gemini/Kiro) + status de sessão.
- **Aceite:** seats reais (vazio se não configurado); device-login funcional; pytest+build verdes.

### FASE 5 — FinOps + Observability + Live (KPIs + efeitos) · Dono: AG-5
- **Spec:** dashboard FinOps (token×seat, rollup, seat ocioso) com componentes KPI premium; Observability (saúde/alertas/links Grafana); Live trace por agente/runtime.
- **Aceite:** dados reais da API; KPIs com micro-animações; build verde.

### FASE 6 — Settings + Inbox + My Issues + Search (Cmd+K) + polish · Dono: AG-6
- **Spec:** Settings (10 abas); Inbox (eventos); My Issues (escopos); Search command palette; micro-interações finais.
- **Aceite:** navegação completa sem 404; build verde.

### FASE 7 — E2E + UI Review (6 pilares) + Perf/A11y · Dono: rotativo
- **Spec:** smoke E2E completo; `gsd-ui-review` (hierarquia, espaçamento, cor/contraste, tipografia, consistência, micro-interações); Lighthouse/perf; acessibilidade.
- **Aceite:** E2E verde; relatório UI-review; sem regressões.

## Dependências / Ondas
- **Onda 1 (paralela):** AG-1 (FASE 0) + backends de AG-2 (FASE 1) e AG-4 (FASE 4) — tokens HEX já existem, então telas podem usar desde já.
- **Onda 2 (paralela):** AG-2 (FASE 2), AG-3 (FASE 3), AG-5 (FASE 5), AG-6 (FASE 6).
- **Onda 3:** FASE 7 (E2E + UI review).

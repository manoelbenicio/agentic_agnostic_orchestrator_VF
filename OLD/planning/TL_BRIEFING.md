# 🧠 BRIEFING DO TECH-LEAD — AOP GSD Agentic Build
**Para:** Tech-Lead / Orchestrator (ex.: Kiro_Opus-48) · **De:** Kiro (planejamento)
**Ação do TL:** ler este plano e **injetar cada prompt abaixo no pane do agente correspondente** (via HerdMaster dispatch / Herdr `pane run`), monitorar e validar os check-outs.

---

## 0. Regras globais (valem para TODOS os agentes)
- **Design System: Indra DSS v3.0 — HEXADECIMAL only** (sem OKLCH). Tokens já aplicados em `AOP/web/src/app/globals.css`. Paleta: deep `#002B3A`, dark `#003E50`, primary `#06596E`, **cyan `#00B0BD` (accent)**, teal `#3F96AE`, sky `#BADFF3`, ink `#00475A`, line `#C7CBC5`, success `#27AE60`, warning `#FF9800`, error `#E91E63`, gold `#FFC107`.
- **Produto:** web app disruptivo, **menu lateral esquerdo**, efeitos/micro-interações premium, experiência Fortune 500.
- **ZERO mock/placeholder em produção** — vazio = empty state real consumindo API.
- **Governança (OBRIGATÓRIA — o TL deve recusar check-out sem isto):** todo agente registra, em
  **`/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/CHECKIN_OUT_GSD.md`** (raiz, append-only):
  (a) **CHECK-IN antes de iniciar qualquer atividade** (timestamp UTC + nome do agente + paths);
  (b) **CHECK-OUT ao terminar** com **timestamp + nome do agente + EVIDÊNCIA REAL incluindo PRINT/SCREENSHOT**
  (salvar em `AOP/.planning/evidence/<AGENTE>-<task>.png` e referenciar o caminho) + saída de pytest/build/curl + SHA256.
  Sem CHECK-IN prévio = violação. CHECK-OUT sem print/evidência = **inválido** (não conta como concluído).
- **Isolamento de paths** — cada agente escreve só no seu escopo. Importa/lê o resto read-only.
- **GSD:** Discuss(rápido)→Plan→Execute→Verify→Ship. Resumo de 3 linhas no fim.

## 1. Ondas de dispatch
- **Onda 1 (injetar já, paralelo):** AG-1, AG-2(backend), AG-4(backend).
- **Onda 2 (após AG-1 shell e backends):** AG-2(UI), AG-3, AG-5, AG-6.
- **Onda 3:** FASE 7 (E2E + UI review).
O TL injeta a Onda 1 imediatamente; ao receber CHECK-OUT, injeta a Onda 2; depois a Onda 3.

---

## 2. PROMPTS INJETÁVEIS (um por pane)

### → PANE AG-1 (Design System + Shell)
```
Você é AG-1. Construa o Design System Indra (HEX) + Shell premium da AOP.
DESIGN: use SOMENTE os tokens HEX já em AOP/web/src/app/globals.css (Indra DSS). Sem OKLCH, sem cor hardcoded fora dos tokens.
ESCOPO: AOP/web/src/components/ui/**, AOP/web/src/components/app-shell.tsx, AOP/web/src/components/page-kit.tsx, AOP/web/src/lib/theme*. NÃO toque em outras telas.
TAREFA: biblioteca de componentes (Button/Input/Select/Dialog/Dropdown/Tabs/Table/Card/Badge/Toast/Tooltip/Skeleton/EmptyState/Avatar) usando os tokens; MENU LATERAL esquerdo agrupado (Visão geral/Construir/Operar/Workspace) com estado ativo (barra accent), header com busca(Ctrl+K)/tema/status; micro-interações sutis (fade/float/wipe). Light/dark.
GOVERNANÇA: CHECK-IN/CHECK-OUT em /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/CHECKIN_OUT_GSD.md com evidência.
ACEITE: componentes com tokens HEX; shell alinhado e responsivo; `npm run build` verde (colar saída) + screenshot. Resumo 3 linhas.
```

### → PANE AG-2 (Projects + Issues)
```
Você é AG-2. Construa Projects e Issues (backend + UI), visual Indra HEX.
ESCOPO: AOP/web/src/app/{projects,issues}/**, AOP/web/src/components/{projects,issues}/**, AOP/control-plane/projects_api/** + registrar rotas em AOP/control-plane/app/main.py (só as rotas). NÃO toque em outras telas/módulos.
BACKEND: tabela Postgres `projects` + CRUD (POST/GET/GET{id}/PATCH/DELETE) + vínculo task↔project. Tasks: usar POST /tasks com operation_mode (terminal|socket).
UI Projects: lista+board, criar/editar/excluir, progresso real. UI Issues: kanban (Backlog→Done)+List/Swimlane/Gantt, modal criar com seletor terminal/socket, detalhe com timeline+painel live(WS)+execution logs, bulk actions. Consumir API real (sem mock; empty state real).
GOVERNANÇA: CHECK-IN/CHECK-OUT no ledger raiz com evidência (pytest + build + curls /projects e /tasks).
ACEITE: CRUD real; criar+despachar nos 2 modos; pytest+build verdes. Resumo 3 linhas.
```

### → PANE AG-3 (Squad Builder v2 + Agents)
```
Você é AG-3. Evolua o Squad Builder (canvas) e a tela Agents, visual Indra HEX.
ESCOPO: AOP/web/src/app/{squad-builder,agents}/**, AOP/web/src/components/{squad-builder,agents}/**. Pode LER control-plane (topology/registry) e HerdMaster (ACL) read-only. NÃO modifique backend de outros.
TAREFA: canvas (@xyflow/react) com paleta+contagem por vendor; DEFINIR PAPEL por nó (worker↔Tech-Lead); EXCLUIR nó in-canvas; salvar/validar topologia (vira ACL via /squads/{id}/topology); hub-and-spoke default-deny. Tela Agents: registry CRUD (estado/saúde/runtime/seat).
GOVERNANÇA: CHECK-IN/CHECK-OUT no ledger raiz com evidência (build + curls topology/agents).
ACEITE: ops de nó funcionando sem reload; topologia→ACL real; build verde. Resumo 3 linhas.
```

### → PANE AG-4 (Seats + Sessions/OAuth)
```
Você é AG-4. Construa Seats (provisionamento) e Sessions/OAuth (device-login), visual Indra HEX.
ESCOPO: AOP/web/src/app/{seats,sessions}/**, AOP/web/src/components/{seats,sessions}/**, AOP/control-plane/{seats_api,sessions_api}/** + rotas em app/main.py. NÃO toque em outros módulos.
BACKEND: endpoints de provisionamento de seats (register/update/remove) — REMOVER o seat hardcoded; device-login por vendor (Codex/Claude/Gemini/Kiro) + status de sessão, isolamento por seat (HOME/config-dir). Sem dado fake.
UI: tela Seats (registrar/editar/remover, lease/available real); tela Sessions (device code, status, renovar/login).
GOVERNANÇA: CHECK-IN/CHECK-OUT no ledger raiz com evidência (pytest + build + curls).
ACEITE: seats reais (vazio se não configurado); device-login funcional; pytest+build verdes. Resumo 3 linhas.
```

### → PANE AG-5 (FinOps + Observability + Live)
```
Você é AG-5. Construa FinOps, Observability e Live com componentes KPI premium, visual Indra HEX + micro-animações.
ESCOPO: AOP/web/src/app/{finops,observability,live}/**, AOP/web/src/components/{finops,observability,live}/**. Consumir API real (finops/tracing/health). NÃO toque em backend de outros.
TAREFA: FinOps (token×seat, rollup por projeto, seat ocioso) com KPI cards/gauges/progress (princípios visual-kpi-designer, sem código pptx); Observability (saúde/coupling/alertas + links Grafana); Live (trace por agente/runtime via WS + fallback). Efeitos sutis (fade/float), tom executivo (headlines = conclusão).
GOVERNANÇA: CHECK-IN/CHECK-OUT no ledger raiz com evidência (build + curls + screenshot).
ACEITE: dados reais; KPIs com micro-animações; build verde. Resumo 3 linhas.
```

### → PANE AG-6 (Settings + Inbox + My Issues + Search + polish)
```
Você é AG-6. Construa Settings, Inbox, My Issues e Search (Cmd+K), e dê o polish final de animações, visual Indra HEX.
ESCOPO: AOP/web/src/app/{settings,inbox,my-issues}/**, AOP/web/src/components/{settings,inbox,my-issues,search}/**. NÃO toque em backend de outros.
TAREFA: Settings (10 abas: General/Members/Repositories/GitHub/Integrations/Profile/Preferences/Notifications/API Tokens/Labs); Inbox (eventos, read/unread, bulk archive); My Issues (escopos All/Assigned/Created/My Agents); Search command palette (cmdk, grupos, teclado); micro-interações finais consistentes.
GOVERNANÇA: CHECK-IN/CHECK-OUT no ledger raiz com evidência (build + screenshot).
ACEITE: navegação completa sem 404; build verde; consistência visual. Resumo 3 linhas.
```

---

## 3. Como o TL injeta (HerdMaster/Herdr)
Para cada agente, o TL injeta o prompt no pane correspondente, ex.:
- `herdmaster tasks create --title "AG-1 design system" --assigned-to <pane_id> --prompt "<conteúdo AG-1>"` (modo socket), ou
- `herdr pane run <pane_id> "<comando do agente com o prompt>"` (modo terminal).
O TL **monitora** o ledger raiz; ao ver CHECK-OUT COMPLETED com evidência, valida e injeta a próxima onda. Se um agente travar (sem progresso), o TL reenfileira/reinjeta (watchdog).

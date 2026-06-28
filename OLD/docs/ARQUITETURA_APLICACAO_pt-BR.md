# Arquitetura da Aplicação — Agnostic Orchestration Platform (AOP)
**Documento de UX/Arquitetura — revisão tela por tela**
**Idioma:** pt-BR · **Versão:** 1.0 · **Autoria:** Kiro (Tech-Lead)

> Este documento descreve **toda a aplicação**: cada tela, layout, menu, botão, opção, feature e estado.
> Cada seção tem: Objetivo · Rota · Status · Layout (wireframe) · Menus · Botões · Features/Opções · Estados · Backend · Critérios de revisão.
> **Status legenda:** ✅ implementado · 🟡 parcial · ⬜ a construir.
> **Nota de licença/branding:** o visual reproduz o **design system** (tokens OKLCH) de referência; componentes são implementação própria; marca = "Agnostic Orchestration Platform" (sem logo/código de terceiros verbatim).

---

## Índice
0. Princípios de Design & Design System
1. Shell Global (Header + Sidebar)
2. Login / Autenticação (OAuth Device)
3. Dashboard
4. Projects (Lista · Board · Detalhe · CRUD)
5. Issues/Tasks (Tracker · Detalhe · Criar · Despachar)
6. Squad Builder (Canvas)
7. Live Panel (Tracing por agente/runtime)
8. Agents (Registry)
9. Seats (Pool / Provisionamento)
10. Sessions / OAuth (Login dos CLIs)
11. FinOps (Custos)
12. Observability (Saúde / Alertas / Grafana)
13. Skills
14. Inbox (Notificações)
15. My Issues
16. Search (Command Palette Cmd+K)
17. Settings (10 abas)
18. Matriz de status & checklist de revisão

---

## 0. Princípios de Design & Design System

- **Local-first**, leve, responsivo, light/dark.
- **Stack:** Next.js (App Router) + Tailwind + shadcn/ui (Radix) + @xyflow/react.
- **Tokens (OKLCH)** — fonte: design-tokens extraídos.
  - Cores: `--bg`, `--bg-2/3`, `--line`, `--fg`, `--fg-dim/mute`, `--accent`, `--ok/green`, `--warn/amber`, `--err/red`, `--blue` (light + dark).
  - Tipografia: UI = Inter; código/terminal = Geist/JetBrains Mono; serif editorial = Source Serif.
  - Raio: 10px (cards) / 8px (controles). Spacing scale Tailwind.
- **Componentes base:** Button (primary/secondary/ghost/destructive), Input, Select, Dialog/Modal, Dropdown, Tabs, Table, Card, Badge/Tag, Toast, Tooltip, Skeleton, EmptyState, Avatar, Resizable panels.
- **Estados obrigatórios em toda tela com dados:** loading (skeleton), error (com Retry), empty (mensagem + CTA), populated. **Zero dado mockado** — vazio mostra empty real.

---

## 1. Shell Global (Header + Sidebar) — Status: 🟡

**Objetivo:** moldura única de navegação presente em todas as telas autenticadas.

**Layout:**
```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ [◧ AOP]  [Workspace ▾]            [🔎 Search (Ctrl+K)]      [● API ok] [☀/🌙/🖥] [👤▾]│  ← Header (56px, sticky)
├──────────────┬────────────────────────────────────────────────────────────────────┤
│ SIDEBAR      │  CONTENT (rota ativa)                                               │
│ ───────────  │                                                                     │
│ ▣ Dashboard  │                                                                     │
│ ▤ Projects   │                                                                     │
│ ✓ Issues     │                                                                     │
│ ⬡ Squad      │                                                                     │
│ ((•)) Live   │                                                                     │
│ ◉ Agents     │                                                                     │
│ ▥ Seats      │                                                                     │
│ ⚷ Sessions   │                                                                     │
│ $ FinOps     │                                                                     │
│ ▦ Observ.    │                                                                     │
│ ★ Skills     │                                                                     │
│ ✉ Inbox (3)  │                                                                     │
│ ───────────  │                                                                     │
│ ⚙ Settings   │                                                                     │
└──────────────┴────────────────────────────────────────────────────────────────────┘
```

**Header — botões/itens (todos):**
| Item | Tipo | Ação |
|---|---|---|
| Logo AOP | link | volta ao Dashboard |
| Workspace ▾ | dropdown | trocar workspace/tenant |
| Search (Ctrl+K) | botão/atalho | abre Command Palette (§16) |
| API status | badge | `API ok`/`API offline` + tooltip do coupling (connected/degraded) |
| Tema | toggle 3-estados | Light / Dark / System |
| Usuário ▾ | dropdown | Perfil, Preferências, Logout |

**Sidebar:** itens de navegação acima; badge de contagem no Inbox; item ativo destacado; colapsável.

**Backend:** `/health` (status + coupling) alimenta o badge; WebSocket para contadores.
**Status atual:** header e sidebar existem com Dashboard/Squad/Live; faltam os demais itens de menu.
**Revisão:** [ ] header completo · [ ] sidebar com todos os itens · [ ] workspace switcher · [ ] badge coupling.

---

## 2. Login / Autenticação (OAuth Device) — Status: ⬜

**Objetivo:** autenticar o usuário sem API key (OAuth Device Flow / SSO).

**Layout:**
```
┌───────────────────────────────────────────────┐
│                  ◧ AOP                          │
│        Agnostic Orchestration Platform          │
│                                                 │
│   ┌─────────────────────────────────────────┐  │
│   │  Entrar                                   │ │
│   │  [ Continuar com Google      ]            │ │
│   │  [ Continuar com Microsoft   ]            │ │
│   │  ─────────  ou  ─────────                 │ │
│   │  Device code:  ┌──────────┐               │ │
│   │                │ EE08-AE6C│  [Copiar]      │ │
│   │                └──────────┘               │ │
│   │  Abra github.com/login/device e autorize  │ │
│   │  ◐ aguardando autorização...              │ │
│   └─────────────────────────────────────────┘  │
└───────────────────────────────────────────────┘
```
**Botões:** Continuar com Google · Continuar com Microsoft · Copiar código · (auto-poll).
**Estados:** aguardando · autorizado→redirect · expirado (re-gerar) · negado.
**Backend:** `/auth/device/authorize`, `/auth/device/token` (polling), JWT.
**Revisão:** [ ] SSO Google/MS · [ ] device code · [ ] polling · [ ] expiração.

---

## 3. Dashboard — Status: ✅ (base)

**Objetivo:** visão geral operacional do workspace.

**Layout:**
```
┌────────────────────────────────────────────────────────────────────────┐
│ Agnostic Orchestration Platform              [API ok] [Live Panel] [Open]│
│ Enterprise control surface…                                              │
│ ┌──────────────────────────────────┐  ┌──────────────────────────────┐  │
│ │ (hero / descrição)               │  │ Execution Modes               │  │
│ │                                  │  │  ▸ Terminal mode               │  │
│ └──────────────────────────────────┘  │  ▸ Socket mode                 │  │
│                                        │  ▸ Visual builder              │  │
│ ┌─ Agents ───────────────────────────┴──────────────────────────────┐  │
│ │  (cards de agentes · estado · burn)  | "No agents registered"      │  │
│ └────────────────────────────────────────────────────────────────────┘  │
│ Seat Pool   0/1 leased                                                   │
│  ┌ codex · available ┐  ┌ + ┐                                            │
│ FinOps  tenant-a/project-a                                               │
│  [Total $] [Token $] [Seat $] [Records]                                  │
└────────────────────────────────────────────────────────────────────────┘
```
**Botões:** Live Panel · Open workspace · Retry (por card) · (futuro) filtros por tenant/projeto.
**Features:** cards Agents, Seat Pool (lease/available), FinOps (Total/Token/Seat/Records), Execution Modes (explicação dos 3 modos).
**Estados:** loading/error/empty por card.
**Backend:** `/agents`, `/seats`, `/finops/.../rollup`, `/health`.
**Revisão:** [ ] cards reais (sem seat fake) · [ ] filtro tenant/projeto · [ ] burn por agente.

---

## 4. Projects — Status: ⬜ (backend e UI a construir)

**Objetivo:** agrupar trabalho (sprints/epics/workstreams); base estrutural do sistema.

**4.1 Lista/Board:**
```
┌───────────────────────────────────────────────────────────────────────┐
│ Projects                              [ + Novo Projeto ]  [Lista|Board] │
│ Filtros: [Status ▾] [Lead ▾] [🔎]                                        │
│ ┌────────────┐ ┌────────────┐ ┌────────────┐                            │
│ │ 🟢 Portal   │ │ ⏸ Migração │ │ ✅ Refactor │   (cards de progresso)    │
│ │ MUL · 12/30 │ │ API · 3/9  │ │ Auth · 9/9 │                            │
│ │ lead: Kiro  │ │ lead: —    │ │ ▓▓▓▓▓▓▓▓░  │                            │
│ └────────────┘ └────────────┘ └────────────┘                            │
└───────────────────────────────────────────────────────────────────────┘
```
**4.2 Modal "Novo Projeto":** campos Nome, Key (auto), Ícone, Status, Lead, Descrição · botões [Criar] [Cancelar].
**4.3 Detalhe do projeto:** metadados + tracker de issues escopado + editar/excluir.
**Botões (todos):** Novo Projeto · alternar Lista/Board · Editar · Excluir (confirmação) · Mudar status · Definir lead · filtros.
**Estados:** loading/error/empty ("nenhum projeto — criar o primeiro").
**Backend (a criar):** tabela `projects` + `POST/GET/GET{id}/PATCH/DELETE /projects` + vínculo task↔project.
**Revisão:** [ ] criar A · [ ] criar B · [ ] editar · [ ] excluir · [ ] board · [ ] progresso real.

---

## 5. Issues/Tasks (Tracker) — Status: ⬜ (UI) / 🟡 (POST /tasks existe)

**Objetivo:** criar, despachar e acompanhar tarefas executadas pelos agentes.

**5.1 Tracker (4 modos de visão):**
```
┌───────────────────────────────────────────────────────────────────────┐
│ Issues   [List|Board|Swimlane|Gantt]   [ + Nova Task ]  [Filtros ▾] [⋮] │
│ ───────────────────────────────────────────────────────────────────── │
│ Backlog │ Todo │ In Progress │ In Review │ Blocked │ Done               │
│ [card]  │[card]│  [card]     │           │         │ [card]             │
│         │      │  AGY-12 ▸   │                                          │
└───────────────────────────────────────────────────────────────────────┘
```
**5.2 Modal "Nova Task":** Título, Descrição (editor), Prioridade, Assignee (agente/seat), Projeto, **Modo de operação: ( ) Terminal ( ) Socket**, Due date · [Criar & Despachar] [Criar] [Cancelar].
**5.3 Detalhe da Issue:** descrição + timeline de atividade + **painel "Agent Working" (live)** + execution logs + properties sidebar (status/priority/assignee/labels/datas) + comentários/@mentions.
**Botões (todos):** Nova Task · alternar 4 visões · drag-and-drop de status (board) · bulk actions (status/priority/assignee/delete) · menu de contexto (clique direito) · Despachar/Re-despachar · Cancelar task · comentar.
**Ciclo de vida:** queued→claimed→running→blocked→done/failed (refletido no card + timeline).
**Backend:** `/tasks` (criar/dispatch via ModeRouter), `/tracing/agents/{id}` (live), eventos de ciclo.
**Revisão:** [ ] criar task · [ ] escolher modo terminal/socket · [ ] board drag-drop · [ ] detalhe + live · [ ] bulk actions.

---

## 6. Squad Builder (Canvas) — Status: 🟡 (canvas existe; faltam ops de nó)

**Objetivo:** montar squad arrastando blocos de agente e definindo **quem fala com quem** (topologia → ACL).

**Layout:**
```
┌───────────────────────────────────────────────────────────────────────┐
│ Squad Builder   [Salvar] [Validar] [Limpar]        Squad: [ ▾ ] [+ Novo]│
│ ┌ Paleta ─────┐  ┌ Canvas (xyflow) ───────────────────────────────────┐│
│ │ + Codex      │  │            ┌────────┐                              ││
│ │ + Antigravity│  │            │ TL ★   │  (Tech-Lead, hub)            ││
│ │ + Gemini     │  │           ╱│        │╲                             ││
│ │ + Kiro       │  │      ┌────┘ └───┐ └────┐                           ││
│ │ + Cursor     │  │      │ Codex#1 │ │Gemini│  (workers)               ││
│ │ (contagem)   │  │      └─────────┘ └──────┘                          ││
│ └──────────────┘  └────────────────────────────────────────────────────┘│
│  Nó selecionado: [Papel: Worker ▾ → promover a Tech-Lead] [Excluir nó]   │
│  Aresta: A→B (permitida) · default-deny lateral · [Conceder] [Revogar]   │
└───────────────────────────────────────────────────────────────────────┘
```
**Botões (todos):** adicionar bloco (por vendor + contagem) · arrastar/posicionar · desenhar conexão (aresta) · **definir papel do nó (Worker↔Tech-Lead)** · **excluir nó** (sem reload) · conceder/revogar aresta lateral · Salvar · Validar topologia · Limpar.
**Regra:** hub-and-spoke — TL fala com todos; workers só com TL; lateral negada salvo concessão explícita.
**Backend:** `/squads/{id}/topology` (salvar/ler, vira ACL), `/agents` (papel/delete).
**Status atual:** canvas + salvar/ler topologia ✅; **faltam**: definir papel no nó, excluir nó in-canvas, paleta com contagem.
**Revisão:** [ ] paleta+contagem · [ ] papel por nó · [ ] excluir nó · [ ] conceder/revogar lateral · [ ] validar.

---

## 7. Live Panel — Status: ✅ (base)

**Objetivo:** monitorar em tempo real cada agente/runtime.

**Layout:**
```
┌───────────────────────────────────────────────────────────────────────┐
│ Live Panel    [Agente ▾ | Runtime ▾]   ● streaming (WS)                 │
│ ┌ Lista ────┐ ┌ Trace (tempo real) ─────────────────────────────────┐  │
│ │ ● Codex#1 │ │ 12:03 thinking: analisando…                          │  │
│ │ ● Gemini  │ │ 12:03 tool_call: file_read(src/api)                  │  │
│ │ ○ Kiro    │ │ 12:04 state: working → done                          │  │
│ │           │ │ burn: 1.2k tokens · seat 00:42                       │  │
│ └───────────┘ └──────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
```
**Botões/Opções:** selecionar agente/runtime · pausar/seguir stream · filtrar por tipo (thinking/tool/state/error) · ver burn individual.
**Backend:** `/ws/tracing/agents/{id}` (WS) + `/tracing/agents/{id}` (REST fallback) + `/tracing/runtimes/{id}`.
**Revisão:** [ ] por agente · [ ] por runtime · [ ] burn individual · [ ] filtros.

---

## 8. Agents (Registry) — Status: ⬜ (UI) / 🟡 (API)

**Objetivo:** registro único de agentes (fonte de verdade) — add/remove propaga automaticamente.
**Layout:** tabela (Label, Vendor/tipo, Papel, Estado, Saúde, Pane/runtime, Seat) + [+ Registrar agente] + ações (editar papel, remover).
**Botões:** Registrar · Editar · Remover (com confirmação) · filtros por estado/saúde.
**Backend:** `/agents` (CRUD) + propagação real (ACL/allowlist/observabilidade).
**Revisão:** [ ] registrar · [ ] remover propaga · [ ] identidade estável.

---

## 9. Seats (Pool / Provisionamento) — Status: ⬜ (UI) / 🟡 (pool em memória)

**Objetivo:** gerenciar os "seats" (assinaturas) por tenant/vendor.
**Layout:**
```
┌───────────────────────────────────────────────────────────┐
│ Seat Pool        [ + Registrar Seat ]   filtro [Vendor ▾]  │
│ ┌ codex#1 · tenant-a · available ┐ ┌ opus#1 · leased ┐     │
│ │ home: /seats/codex1            │ │ por: AGY-12      │     │
│ │ [Liberar] [Editar] [Remover]   │ │ [Forçar release] │     │
│ └────────────────────────────────┘ └──────────────────┘     │
└───────────────────────────────────────────────────────────┘
```
**Botões:** Registrar Seat (vendor, tenant, home/config-dir) · Editar · Remover · Liberar/Forçar release · ver afinidade/lease.
**Backend (a criar):** endpoints de provisionamento de seats (register/update/remove) — **remover o seat hardcoded**.
**Revisão:** [ ] registrar seat real · [ ] editar · [ ] remover · [ ] estado lease/available real.

---

## 10. Sessions / OAuth (Login dos CLIs) — Status: ⬜

**Objetivo:** autenticar os CLIs de agente (Codex/Claude/Gemini/Kiro) por **device-login**, por seat, sem sobrescrever sessão.
**Layout:**
```
┌───────────────────────────────────────────────────────────┐
│ Sessions                         [ + Nova sessão ]         │
│ Vendor   Seat        Status        Expira    Ações         │
│ Codex    codex#1     ● connected   29d       [Renovar][↩]  │
│ Gemini   gemini#1    ◐ pending…    —          (device code)│
│ Kiro     kiro#1      ✗ expired      —         [Login]      │
│ Device code: ABCD-1234  → abra a URL e autorize            │
└───────────────────────────────────────────────────────────┘
```
**Botões:** Nova sessão (escolhe vendor+seat) · Login (gera device code) · Renovar · Revogar · Copiar código.
**Backend (a criar):** device-login por vendor + status de sessão; isolamento por seat (HOME/config-dir).
**Revisão:** [ ] device login por vendor · [ ] multi-sessão sem colisão · [ ] status/expiração.

---

## 11. FinOps (Custos) — Status: 🟡 (API) / ⬜ (tela dedicada)

**Objetivo:** custo por token e por seat, atribuição hierárquica, modos de billing.
**Layout:** filtros (tenant/projeto/agente/runtime/período) + cards (Total/Token/Seat/Records) + tabela de atribuição (tenant→projeto→issue→agente→runtime) + gráfico de burn + detecção de seat ocioso + modo billing (pay-as-you-go/mensal).
**Botões:** filtrar · exportar (CSV) · alternar token/seat · ver right-sizing.
**Backend:** `/finops/costs/token`, `/finops/costs/seat`, `/finops/.../rollup`.
**Revisão:** [ ] rollup por projeto · [ ] token vs seat · [ ] seat ocioso · [ ] export.

---

## 12. Observability — Status: ✅ (stack) / ⬜ (tela na app)
**Objetivo:** saúde do sistema, alertas e atalhos para Grafana/Prometheus.
**Layout:** cards de saúde (coupling, postgres, redis, herdmaster), lista de alertas ativos (Alertmanager), links para dashboards Grafana (HerdMaster + AOP FinOps/Tracing), gráfico de quota/burn.
**Botões:** abrir Grafana · abrir Prometheus · reconhecer alerta · filtrar período.
**Backend:** `/health`, `/health/ready`, `/metrics`, Alertmanager API.
**Revisão:** [ ] saúde · [ ] alertas · [ ] quota/burn · [ ] links Grafana.

---

## 13. Skills — Status: ⬜
**Objetivo:** biblioteca de habilidades reutilizáveis atribuíveis a agentes.
**Layout:** lista (origem, atribuições) + Nova Skill (manual / import URL / copy from runtime) + editor 3 colunas (árvore de arquivos · editor · metadados) + atribuição a agentes.
**Botões:** Nova Skill · Importar URL · Copy from runtime · Editar · Atribuir · Remover.
**Revisão:** [ ] criar · [ ] importar · [ ] atribuir.

---

## 14. Inbox (Notificações) — Status: ⬜
**Objetivo:** hub de eventos (atribuições, status, atividade de agente, comentários…).
**Layout:** painel redimensionável (lista à esquerda, detalhe à direita) + read/unread + bulk archive + tipos de evento com ícones.
**Botões:** marcar lido/não lido · arquivar · arquivar em massa · filtrar por tipo · abrir item.
**Revisão:** [ ] tipos de evento · [ ] read/unread · [ ] bulk archive.

---

## 15. My Issues — Status: ⬜
**Objetivo:** visão pessoal filtrada.
**Layout:** tabs de escopo (All / Assigned / Created / My Agents) + 3 modos de visão + filtro rápido "Agents working" + agrupar por status/assignee.
**Botões:** trocar escopo · trocar visão · filtro rápido · agrupar.
**Revisão:** [ ] escopos · [ ] agrupamento.

---

## 16. Search (Command Palette Cmd+K) — Status: ⬜
**Objetivo:** busca global e comandos.
**Layout:** overlay central (cmdk) com grupos: Issues · Projects · Pages · Commands · Members · Agents · debounce 300ms · navegação por teclado · highlight.
**Botões/atalhos:** Ctrl/Cmd+K abrir · setas navegar · Enter executar · Esc fechar.
**Revisão:** [ ] grupos · [ ] navegação teclado · [ ] comandos.

---

## 17. Settings (10 abas) — Status: ⬜
**Objetivo:** configuração do workspace e conta.
**Abas:** General (nome/slug/prefixo/contexto) · Members (convidar/papéis/permissões) · Repositories (URLs git) · GitHub (OAuth app) · Integrations (Lark/Feishu, etc.) · Profile · Preferences (tema/idioma/timezone) · Notifications · API Tokens (criar/revogar/reveal único) · Labs.
**Botões (por aba):** salvar · convidar membro · gerar/revogar token · conectar integração · alternar preferências.
**Revisão:** [ ] 10 abas · [ ] members/roles · [ ] api tokens · [ ] preferences.

---

## 18. Matriz de Status & Checklist de Revisão

| # | Tela | Status | Backend | Prioridade |
|---|---|---|---|---|
| 1 | Shell Global | 🟡 | /health | Alta |
| 2 | Login/OAuth | ⬜ | auth/device | Média |
| 3 | Dashboard | ✅ base | agents/seats/finops | — |
| 4 | Projects | ⬜ | a criar | **Alta** |
| 5 | Issues/Tasks | ⬜ UI / 🟡 API | /tasks | **Alta** |
| 6 | Squad Builder | 🟡 | /squads/topology | **Alta** |
| 7 | Live Panel | ✅ base | /ws/tracing | — |
| 8 | Agents | ⬜ UI / 🟡 API | /agents | Alta |
| 9 | Seats | ⬜ UI | a criar | **Alta** |
| 10 | Sessions/OAuth | ⬜ | a criar | **Alta** |
| 11 | FinOps | 🟡 | /finops | Média |
| 12 | Observability | ✅ stack / ⬜ tela | /health,/metrics | Média |
| 13 | Skills | ⬜ | a criar | Baixa |
| 14 | Inbox | ⬜ | a criar | Baixa |
| 15 | My Issues | ⬜ | /tasks | Baixa |
| 16 | Search | ⬜ | agregador | Média |
| 17 | Settings | ⬜ | a criar | Média |

**Como revisar:** percorra as seções 1–17; em cada checklist marque o que aprova/ajusta; me devolva os ajustes por tela que eu incorporo e construo na ordem de prioridade.

# SPEC — FASE 2 · Issues/Tasks (tracker + criar + despachar + detalhe live)
**Dono:** AG-2 · **Status:** blocked-by F1 backend · **Depende de:** F0, F1

## Discuss
Criar/despachar/acompanhar tarefas dos agentes. `POST /tasks` existe; falta UI completa.

## WHAT
- Tracker: 4 visões (List, Board/Kanban Backlog→Done, Swimlane, Gantt); drag-and-drop de status no board.
- Criar task (modal): título, descrição (editor), prioridade, assignee, projeto, **modo de operação (terminal|socket)**, due date; [Criar & Despachar].
- Detalhe: descrição + timeline de atividade + **painel "Agent Working" live (WebSocket)** + execution logs + properties sidebar + comentários.
- Bulk actions (status/priority/assignee/delete); menu de contexto.

## Escopo de paths
`AOP/web/src/app/issues/**`, `components/issues/**`. Lê control-plane (read-only).

## Aceite (UAT)
- [ ] Criar task escolhendo modo terminal E socket; despachar; ciclo de vida real (queued→…→done).
- [ ] Board drag-drop muda status; detalhe mostra trace live.
- [ ] build verde. **Print** em `AOP/.planning/evidence/AG-2-issues.png`.

## Evidência obrigatória
build + curls /tasks + PRINT real no ledger raiz.

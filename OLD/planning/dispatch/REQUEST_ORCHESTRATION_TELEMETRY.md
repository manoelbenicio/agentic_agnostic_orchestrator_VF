# REQUEST (arquitetura) — Orchestration Telemetry & Task Lifecycle (OTTL)

**Autor:** Kiro (Senior AI Solutions Architect / planner) · **Executor:** worker via TL · **Prioridade:** P1
**Problema:** hoje o TL só injeta prompt no pane + ledger manual. Não há máquina de estado, não dá pra ver
qual agente está em qual task, % concluído, ETA, nem detectar "agente não fez" ou "TL esqueceu de cobrar".
**Princípio:** **fonte única de verdade = máquina de estado de tasks do HerdMaster (Postgres)**, com **dupla
atestação** (TL cria + agente faz check-in/out apartado) e um **reconciliador** que cruza sinais e alerta.

## Componentes

### 1. Registro de task OBRIGATÓRIO (reusar `herdmaster tasks`)
- O TL **DEVE** `herdmaster tasks create` para CADA dispatch **antes** de injetar o prompt no pane.
- Campos: `title, assignee(agent_id), priority, project, estimate_minutes, acceptance_criteria[], subtasks[]`
  (subtasks vêm do `tasks.md` do OpenSpec). O prompt injetado carrega o `task_id`.
- Máquina de estado: `queued → assigned → in_progress(checkin) → [blocked(ask)] → complete(evidence) | failed(reason)`.
- **Violação:** injetar no pane sem `tasks create` ⇒ reconciliador marca `TL_NO_DISPATCH`.

### 2. Atestação independente do agente (APARTADA do TL)
- O próprio agente chama `herdmaster tasks checkin <id>` ao iniciar (grava agent_id+ts) e
  `herdmaster tasks complete <id> --evidence <png,sha,testes>` ao terminar (ou `fail --reason`).
- Hook automático espelha cada evento no ledger humano `CHECKIN_OUT_GSD.md` ⇒ DB e ledger nunca divergem.
- Duas partes atestam o mesmo fato (TL atribuiu / agente executou) — base da reconciliação.

### 3. Progresso % e ETA (objetivo, não "acho que 80%")
- **% concluído = subtasks_done / subtasks_total** (o agente marca via `herdmaster tasks progress <id> --subtask k --done`).
- **ETA**: dois números exibidos —
  - `eta_plan = max(0, estimate_minutes − elapsed)` (baseado na estimativa do TL no create);
  - `eta_vel  = (remaining_subtasks / done_subtasks) × elapsed` (velocidade empírica, quando ≥1 subtask feita).
- **Heartbeat**: estado (idle/working/blocked) + `last_heartbeat` do herdr; heartbeat velho > T ⇒ `suspect`.

### 4. Reconciliador / detector de desvio (o mecanismo INDIRETO pedido) — job periódico, gera alertas:
| Condição | Alerta |
|---|---|
| task `assigned` sem `checkin` do agente em até `grace` | `AGENT_NO_CHECKIN` |
| agente `working` sem nenhuma task `in_progress` dele | `UNTRACKED_WORK` (TL esqueceu de registrar / freelancing) |
| task `in_progress` mas agente `idle`/heartbeat velho | `STALLED` / `ABANDONED_MIDWAY` |
| atividade atual do pane (path/tópico) fora do escopo da task | `SCOPE_DRIFT` |
| task `complete` sem artefatos de evidência (png/sha/testes) | `INVALID_COMPLETION` |
- Cada alerta ⇒ aparece no board + mensagem automática ao TL para agir (reabrir/reatribuir/cobrar).

### 5. Live Board (ver tudo de relance) — `herdmaster board` (CLI) + painel web `/observability` (frente do AG-5)
Por agente: `task | state | % | elapsed | eta_plan | eta_vel | last_heartbeat | evidence ✓/✗ | flags`.
Atualização contínua; alimentado pela telemetria acima.

### 6. Mandato do orquestrador
A role `orchestrator` **DEVE sempre manter** o registro de tasks + o board vivos. Faz parte da definição do TL:
TL sem board atualizado = violação operacional (reconciliador sinaliza).

## Entregáveis (para o worker)
1. Estender modelo de task do HerdMaster: `estimate_minutes`, `subtasks`, `progress`, `acceptance_criteria` (migration idempotente).
2. Comandos: `tasks progress`, e enforcement do `create` antes do dispatch (hook no caminho de injeção do TL).
3. Hook de espelhamento DB→`CHECKIN_OUT_GSD.md`.
4. Reconciliador periódico (worker/loop) emitindo os 6 alertas acima.
5. `herdmaster board` (CLI) + endpoint `/observability/board` consumido pela UI do AG-5.
6. Testes: cada estado/alerta com teste; smoke do board com 2 tasks simuladas (1 saudável, 1 STALLED).

## Verificação (DoD)
- `herdmaster tasks list` mostra as tasks reais da Onda 1 (não vazio) com % e ETA.
- Forçar `STALLED` (matar heartbeat) ⇒ alerta aparece no board e mensagem ao TL.
- Injeção sem `tasks create` ⇒ `TL_NO_DISPATCH`.
- CHECK-OUT sem evidência ⇒ `INVALID_COMPLETION`.
- CHECK-IN/CHECK-OUT no ledger + PRINT em `AOP/.planning/evidence/OTTL.png`. Zero mock.

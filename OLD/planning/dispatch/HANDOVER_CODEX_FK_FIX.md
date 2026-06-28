# HANDOVER → CODEX (worker) — Fix durável do HerdMaster (Postgres)

**De:** Kiro (planner) · **Para:** Codex worker (via TL) · **Prioridade:** P0 (bloqueia dispatch)
**Repo:** `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/` · **Branch:** `build/initial-stable`
**Store real:** Postgres container `deploy-postgres-1` (`127.0.0.1:5432`, db `aop`, user `aop_dev`, healthy).

## SINTOMA (provado por log)
`herdmaster agents` / `tasks list` / dispatch loop morriam com:
```
psycopg.errors.InFailedSqlTransaction: current transaction is aborted...
```
Causado em cascata pelo erro-raiz:
```
psycopg.errors.ForeignKeyViolation: update or delete on table "agents"
violates constraint "health_events_agent_id_fkey" on table "health_events"
DETAIL: Key (id)=(w8:pJ) is still referenced from table "health_events".
```
Efeito: o control-plane fica `running` mas **não despacha nenhuma task** → nenhum agente trabalha.
Mitigação temporária aplicada por mim: restart limpou a conexão envenenada (volta a quebrar no próximo churn de agente).

## ROOT CAUSE (provado por introspecção)
1. **FK sem ON DELETE CASCADE.** Em TODOS os schemas, `referential_constraints.delete_rule = NO ACTION`
   para `health_events_agent_id_fkey` (e provavelmente outras FKs que referenciam `agents`, ex. `tasks`).
   Quando o reconciler atualiza/remove um agente que tem `health_events`, estoura ForeignKeyViolation.
2. **Sprawl de schema por boot.** O HerdMaster cria um schema novo `hm_<hash>` a cada inicialização
   (vistos: `hm_009de474...`, `hm_00db08ed...`, `hm_00df05da...`, `hm_0111b952...`, `hm_smoke_f0b`, +vários).
   Lixo acumulado entre restarts; o "flush" via sqlite era no store ERRADO (o real é Postgres).

## TAREFAS (faça migration + código, com verificação)
### T1 — Migration: ON DELETE CASCADE nas FKs que referenciam `agents`
- Localizar onde o schema/DDL do HerdMaster é gerado (provável `herdmaster/db/` ou `migrations/` / `schema.sql` / código que faz `CREATE TABLE health_events ... REFERENCES agents`).
- Alterar a FK `health_events_agent_id_fkey` (e auditar `tasks`, `task_events`, qualquer `*_agent_id_fkey`)
  para `ON DELETE CASCADE` (ou `ON DELETE SET NULL` onde fizer sentido semântico).
- Escrever uma migration idempotente que faça, para cada schema existente e para o template de novos schemas:
  ```sql
  ALTER TABLE health_events DROP CONSTRAINT health_events_agent_id_fkey;
  ALTER TABLE health_events ADD CONSTRAINT health_events_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE;
  ```
- Auditar o reconciler de agentes: preferir **UPSERT** (`INSERT ... ON CONFLICT (id) DO UPDATE`) em vez de delete+insert, para não disparar a FK.

### T2 — Sprawl de schema
- Decidir/implementar política: **schema fixo único** (ex. `hm_main`) OU limpeza automática de schemas `hm_*` órfãos no boot.
- Adicionar um comando/op de cleanup: `DROP SCHEMA hm_<hash> CASCADE` para schemas que não são o ativo.
- Garantir que `bootstrap.sh reset-hard` faça o flush no **Postgres** (não no sqlite inexistente).

### T3 — Role do TL (orchestrator)
- `w8:pJ` (kiro/TL) aparece como `role=worker` mesmo com `config.toml [acl]` marcando kiro=orchestrator.
- Corrigir o caminho que aplica role: na sincronização, o role do `config.toml` deve sobrepor o default `worker`
  para o pane do orquestrador. Resultado esperado: `herdmaster agents` mostra `w8:pJ ... role=orchestrator`.

## VERIFICAÇÃO (obrigatória — anexar saída no CHECK-OUT)
1. `herdmaster agents` → roster limpo, `w8:pJ role=orchestrator`, sem erro.
2. Forçar churn: derrubar e re-sincronizar um agente com `health_events` → **sem** ForeignKeyViolation no log.
3. `herdmaster tasks list` e o dispatch loop sem `InFailedSqlTransaction` no `~/.config/herdmaster/hm.log`.
4. `select table_schema,constraint_name,delete_rule from information_schema.referential_constraints ... like '%agent%'` → `CASCADE`.
5. Confirmar só 1 schema ativo (ou cleanup dos `hm_*` órfãos).

## GOVERNANÇA (mandato do operador)
- CHECK-IN antes (timestamp + nome do agente) e CHECK-OUT depois com **PRINT/screenshot** em
  `AOP/.planning/evidence/CODEX-fk-fix.png`, registrados em `CHECKIN_OUT_GSD.md` (raiz). Sem print = inválido.
- Zero mock/placeholder. Migration idempotente e reversível.

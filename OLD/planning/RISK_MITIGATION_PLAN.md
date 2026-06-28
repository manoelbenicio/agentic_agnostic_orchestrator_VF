# PLANO DE MITIGAÇÃO DE RISCO — AOP (vendor-grounded, p/ revisão)
Autor: Kiro (Principal Architect). REGRA: zero achismo — cada mitigação cita doc de fabricante / repo / medição.
Status: PARA REVISÃO DO OPERADOR. Capturar como change OpenSpec após aceite.

## FONTES (vendor / oficiais consultadas)
- [V1] psycopg3 — Transactions management: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- [V2] psycopg3 — Connection pools (Connection quality / check / reset / stats): https://www.psycopg.org/psycopg3/docs/advanced/pool.html
- [V3] PostgreSQL — Foreign keys / referential actions: https://www.postgresql.org/docs/current/ddl-constraints.html
- [V4] PostgreSQL — Schemas / search_path: https://www.postgresql.org/docs/current/ddl-schemas.html
- [V5] Prometheus — scrape_config / jobs: https://prometheus.io/docs/prometheus/latest/configuration/configuration/
- [V6] Grafana — dashboard/datasource provisioning: https://grafana.com/docs/grafana/latest/administration/provisioning/

## REGISTRO DE RISCOS → MITIGAÇÃO (com evidência)
| ID | Risco (ocorreu) | Causa-raiz (dado) | Mitigação VENDOR-GROUNDED | Fonte |
|----|-----------------|-------------------|---------------------------|-------|
| R1 | Transação Postgres abortada derruba dispatch loop | conexão longa reusada após erro sem rollback | **(a)** `conn.rollback()` em todo erro antes de reusar; **(b)** usar `with pool.connection()` (commit/rollback automático ao sair do bloco); **(c)** preferir `autocommit=True` + `with conn.transaction()` só onde precisa atomicidade | [V1] |
| R2 | Conexão "quebrada/abortada" servida ao loop | pool não checa estado da conexão | configurar **`check=ConnectionPool.check_connection`** no pool → conexão ruim é detectada e trocada antes de entregar; `reset` callback p/ limpeza; conexão broken é descartada automaticamente | [V2] |
| R3 | Sem alerta quando o banco cai | sem hook de falha | usar **`reconnect_failed()`** callback (alerta/restart) + `pool.wait()` no startup p/ falhar cedo se mal configurado | [V2] |
| R4 | FK sem ON DELETE CASCADE → ForeignKeyViolation | `health_events_agent_id_fkey`=NO ACTION (medido) | FK com **`ON DELETE CASCADE`** (referential actions) — já aplicado pelo P0; auditar todas as FKs p/ `agents` | [V3] |
| R5 | Sprawl de 557 schemas `hm_*` | schema novo por boot (medido) | schema único + `search_path`; cleanup idempotente de órfãos — aplicado | [V4] |
| R6 | Cegueira de falhas de DB/pool | sem métricas | expor **`pool.get_stats()`** (`returns_bad`, `connections_lost`, `requests_errors`) ao Prometheus (já roda: jobs `herdmaster-internal-metrics:8080`, `aop-control-plane-metrics:8090`) | [V2][V5] |
| R7 | Sem trilha de tasks (tasks=0 medido) | TL injeta no pane, não cria task | OTTL: `herdmaster tasks create` obrigatório → popula `tasks`+`task_audit_log` (who/what/when/ETA) → pesquisa retroativa | medição+design |
| R8 | Agente crasha → task órfã, status incerto | sem heartbeat/realocação | heartbeat (Prometheus `up`/alert_rules.yml já existe) → realocação imediata + retomada idempotente + evidência | [V5]+proc. crash |
| R9 | Observabilidade rasa por agente | dashboards genéricos (corrigido: existem `aop_finops_tracing.json`,`herdmaster_main.json`) | **expandir** Grafana provisioning com dashboards por agente (tokens/custo/latência) e por rota (p95/erro); usar job `herdmaster-e2e-api-monitor` já presente | [V5][V6] |
| R10| Dispatch silenciosamente parado | `herdr send-text` não dá Enter (observado) | sempre `herdr pane run` (texto+Enter) + ler pane p/ confirmar submissão | observação |
| R11| QA prematuro / fake-done sem evidência | testes cedo; check-out raso | QA E2E exaustivo só no FINAL (1x); check-out obrigatório PRINT+SHA; reconciliador marca `INVALID_COMPLETION` | processo |

## ORDEM DE EXECUÇÃO (após sua revisão)
R1+R2+R3+R6 (robustez de DB/pool — código no control-plane/HerdMaster) → R7 (OTTL) → R9 (observabilidade por agente) → reconciliar features rasas → Integração → QA E2E (1x) → Ship.

## DECISÃO QUE PRECISO DE VOCÊ
Aprovar este registro p/ eu capturar como change OpenSpec (`proposal.md`+`specs/`+`tasks.md`) e o TL distribuir aos workers. Eu desenho; workers implementam.

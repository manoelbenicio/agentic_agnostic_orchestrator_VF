# 43 — Teste de Carga e Concorrência

> Plano de teste de carga para a AOP. **Nenhum resultado de carga foi medido** nesta entrega de documentação — abaixo está o **roteiro** que a squad executará, com comandos e metas. Resultados reais devem ser anexados como evidência (ver doc 53).

## 1. Objetivo

Validar que o control-plane (`:8090`) e o acoplamento HerdMaster sustentam a concorrência esperada de uma squad multi-agente (8 agentes em paralelo) e múltiplos tenants/projetos, sem degradar latência nem corromper o FinOps.

## 2. Superfícies a estressar

| Endpoint | Perfil de carga | Métrica-alvo |
|----------|-----------------|--------------|
| `POST /tasks` (socket/terminal) | rajadas concorrentes | latência p95, taxa de erro |
| `POST /finops/costs/token` | alta frequência (custo por turno) | throughput, integridade do rollup |
| `GET /finops/projects/{t}/{p}/rollup` | leitura concorrente | latência, consistência |
| `POST /tracing/events` | alto volume (burn) | throughput, perda zero |
| `WS /ws/tracing/agents/{id}` | N conexões simultâneas | conexões estáveis, sem leak |
| `POST /squads/{id}/messages` | roteamento + ACL | latência, 403 corretos |

## 3. Cenários

1. **Baseline (1 agente):** 1 tenant, 1 projeto, sequência de tasks — estabelece latência de referência.
2. **Squad real (8 agentes):** 8 runtimes concorrentes, 1 TL roteando; mede contention no Postgres/Redis e no message bus.
3. **Multi-tenant:** K tenants × M projetos em paralelo — valida isolamento e que o rollup não mistura atribuição.
4. **FinOps storm:** rajada de `POST /finops/costs/token` (simulando custo por turno de muitos agentes) e leitura simultânea de rollups — valida que `INSERT` + `SUM` agregam corretamente sob carga.
5. **Tracing/WS fan-out:** N clientes WS por agente recebendo o stream — valida o polling de 1s do `/ws/tracing` sob fan-out.

## 4. Ferramentas sugeridas

- **k6** (HTTP + WS, script JS) ou **Locust** (Python) para HTTP.
- **vegeta** para rajadas simples de um endpoint.
- Postgres: `pg_stat_statements` para top queries; Redis: `redis-cli --latency`.
- Observação durante a carga via Grafana (doc 23).

### Cenário k6 implementado

O cenário real está em `e2e/k6/aop-stress.js` e cobre:

- readiness do control-plane;
- frontend dashboard;
- listagens de projetos, task board e inbox;
- health do LLM Gateway e RAG;
- escrita FinOps;
- escrita de tracing;
- rollup FinOps;
- contrato de dispatch `POST /tasks`;
- consulta RAG periódica.

Runner:

```bash
API_BASE=http://127.0.0.1:8095 \
UI_BASE=http://127.0.0.1:13000 \
AOP_K6_PROFILE=smoke AOP_K6_VUS=3 AOP_K6_DURATION=20s \
bash e2e/k6/run-k6.sh
```

Se `k6` não estiver instalado, o runner tenta `docker run --network host grafana/k6:latest`.

## 5. Metas (SLO sugeridos — a calibrar)

| Métrica | Meta inicial |
|---------|--------------|
| `POST /tasks` p95 | < 300 ms (modo stub) |
| `POST /finops/costs/token` p95 | < 150 ms |
| `GET rollup` p95 | < 200 ms |
| Taxa de erro | < 1% |
| Integridade FinOps | `record_count` e `total_cost_usd` batem com o nº de POSTs aceitos |

## 6. Procedimento

```bash
# 1. Subir stack limpo
bash AOP/ops/stop.sh && bash AOP/ops/start.sh
# 2. Backup pré-carga (para resetar depois)
BACKUP_ROOT=/mnt/c/VMs/Projects/AOP/deploy/backups bash AOP/ops/db-backup.sh full
# 3. Rodar o cenário (ex.: k6)
k6 run carga_tasks.js
# 4. Validar integridade do FinOps pós-carga
curl -s http://127.0.0.1:8090/finops/projects/t1/p1/rollup | python3 -m json.tool
# 5. Coletar métricas (Grafana / pg_stat_statements / redis-cli --latency)
# 6. Resetar ambiente de teste
bash AOP/ops/flush-restart.sh   # CONFIRMO (após garantir backup)
```

## 7. Ressalvas importantes

- Enquanto os executores estiverem em **modo stub** (`max_polls=1`, `read_state` único — doc 34), o teste de carga mede o **caminho de contrato**, não a execução real até conclusão. Repetir a carga **depois** de fechar o bloco G do [`42-CHECKLIST-TEST-READY.md`](42-CHECKLIST-TEST-READY.md).
- O ambiente é local/loopback (`127.0.0.1`); números não representam produção distribuída.
- Anexar `evidence` (saída do k6 + screenshots Grafana) ao ledger da squad (doc 53).

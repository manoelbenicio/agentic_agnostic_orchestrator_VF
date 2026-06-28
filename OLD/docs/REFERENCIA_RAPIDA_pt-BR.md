# ⚡ Referência Rápida — Agnostic Orchestration Platform (AOP)
**Versão:** 1.0.0 (2026-06-26) | **Day-2 Team Cheatsheet** (pt-BR)

Este documento reúne comandos rápidos, rotas de API, mapeamento de portas e diagnósticos para atuação rápida no dia a dia da sustentação.

---

## 1. Mapeamento de Portas e Serviços

| Serviço | Porta Local | URL de Teste de Saúde |
| :--- | :--- | :--- |
| **Postgres** | `5432` | `docker exec -it aop-postgres pg_isready` |
| **Redis** | `6379` | `redis-cli ping` |
| **HerdMaster API** | `8080` | `curl http://127.0.0.1:8080/status` |
| **AOP Control Plane** | `8090` | `curl http://127.0.0.1:8090/health` |
| **Prometheus** | `9090` | `http://127.0.0.1:9090/-/healthy` |
| **Grafana** | `3000` | `http://127.0.0.1:3000/api/health` |
| **Alertmanager** | `9093` | `http://127.0.0.1:9093/-/ready` |
| **AOP Frontend** | `13000` | `http://127.0.0.1:13000` |

---

## 2. Comandos Operacionais Essenciais (Day-2)

Sempre executar os scripts a partir de `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/AOP/ops/`:

```bash
# Iniciar a pilha completa (DBs, Web, API, Observabilidade)
bash start.sh

# Desligar todos os serviços de forma graciosa
bash stop.sh

# Expurgo total de logs, cache do Next.js e reinicialização
bash flush-restart.sh
# -> Digitar "CONFIRMO" para limpar banco de dados e caches de filas Redis

# Verificar status completo na console:
# Mostra tabela dinâmica de liveness de todas as portas TCP e HTTP
```

---

## 3. Guia Rápido de APIs (REST via curl)

### Injetar uma nova Tarefa (Task)
```bash
curl -X POST http://127.0.0.1:8090/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-test-01",
    "tenant_id": "tenant-a",
    "project_id": "project-a",
    "assignee_runtime": "w6:p1",
    "prompt": "Fazer auditoria de arquivos residuais e relatar",
    "operation_mode": "socket",
    "seat_seconds": 30
  }'
```

### Consultar Acúmulo de Custos (FinOps Project Rollup)
```bash
curl http://127.0.0.1:8090/finops/projects/tenant-a/project-a/rollup
```

### Visualizar Logs de Traces de um Agente
```bash
curl http://127.0.0.1:8090/tracing/agents/w6:p1
```

### Deletar Agente não autorizado (Purga Manual)
```bash
curl -X DELETE http://127.0.0.1:8090/agents/w6:p9 \
  -H "Authorization: Bearer <HM_TOKEN>"
```

---

## 4. Troubleshooting Flash

### Erro: `"Failed to Fetch"` no Browser / "API offline"
- **Diagnóstico:** O control-plane na porta `8090` está desativado ou as origens CORS estão erradas.
- **Ação:**
  ```bash
  ss -tlnp | grep :8090
  # Se vazio, iniciar:
  bash start.sh
  ```

### Erro: `"database is locked"` no SQLite
- **Diagnóstico:** Acesso concorrente direto de escrita no arquivo `herdmaster.db`.
- **Ação:** Nunca acesse o banco via terminal/sqlite CLI enquanto os agentes estiverem processando tasks. Utilize os endpoints `/agents` e `/tasks` para intermediar as requisições. Se persistir, force a limpeza do checkpoint:
  ```bash
  sqlite3 ~/.config/herdmaster/herdmaster.db "PRAGMA wal_checkpoint(TRUNCATE);"
  ```

### Alerta: `UnlistedAgentsDetected` disparado no Prometheus/Alertmanager
- **Diagnóstico:** Agentes fantasmas foram criados por injeção externa no banco.
- **Ação:** Aguarde o webhook automatizado na porta `9099` remover a ameaça (~45 segundos). Caso falhe, delete manualmente via rota `DELETE /agents/{id}`.

# 25 — Status 360, Dashboard e Flush-Restart

## 1. `status360.py` — dashboard de semáforo + ETA

Origem: `ops/status360.py` (+ launcher `ops/run-dashboard.sh`).

Ferramenta de terminal que cruza um **ledger de check-in/out** com o `herdr pane list` (estado vivo) e renderiza um painel com semáforo (🟢🟡🔴⚪⊘), progresso e ETA por tarefa e total.

```bash
python3 AOP/ops/status360.py            # uma renderização
python3 AOP/ops/status360.py --watch    # refresh a cada 60s
# launcher (terminal WSL separado):
bash AOP/ops/run-dashboard.sh
```

### ⚠️ Estado legado — precisa de ajuste antes de usar

`status360.py` e `run-dashboard.sh` contêm **caminhos hardcoded obsoletos** e um **SCOPE fixo** da rodada anterior:

- `LEDGER = "/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/CHECKIN_OUT_GSD.md"` — caminho **não** corresponde à raiz atual e o arquivo `CHECKIN_OUT_GSD.md` não existe na AOP atual.
- `run-dashboard.sh` aponta `DIR="/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/AOP/ops"`.
- O dicionário `SCOPE` traz tags (`AG-1`..`AG-6`, `P0`, `F7`...) e agentes da squad **anterior** (ex.: `AGY_OPUS46`, `AGY_Gemini-PRO31`).

**Decisão:** o protocolo de check-in/out **novo** está definido em [`50-GOVERNANCA-SQUAD/53-PROTOCOLO-CHECKIN-OUT.md`](../50-GOVERNANCA-SQUAD/53-PROTOCOLO-CHECKIN-OUT.md), com ledger em disco no diretório do projeto. Se a squad quiser reusar o `status360.py`, deve:
1. Apontar `LEDGER` para o novo ledger (ex.: `/mnt/c/VMs/Projects/AOP/CHECKIN_OUT.md`).
2. Atualizar `SCOPE`/`tag_of` para os papéis/tags da squad atual (8 agentes — ver doc 51).
3. Corrigir o `DIR` em `run-dashboard.sh`.

> Tratar `status360.py` como **utilitário opcional legado**, não como fonte de verdade. A tabela canônica de status do stack é o `print_status_table` de `common.sh` (ver doc 21).

---

## 2. `flush-restart.sh` — reset e religada

Origem: `ops/flush-restart.sh`.

Fluxo:
1. `stop.sh` completo.
2. **Flush não-destrutivo** (sempre): apaga `ops/logs/*`, PID files, `web/.next/cache`, `.pytest_cache`, `__pycache__`, `*.pyc`, prompts em `RUNTIME_DIR`.
3. **Prompt interativo**:
   ```
   Type CONFIRMO to reset AOP Postgres schemas and Redis; anything else preserves DB/Redis:
   ```
4. Se digitar exatamente **`CONFIRMO`** → caminho **destrutivo**:
   - Sobe postgres/redis, espera healthy.
   - `DROP SCHEMA` de todos os schemas `aop\_%`.
   - `redis-cli FLUSHALL`.
   - `DROP TABLE` das tabelas públicas: `messages`, `tasks`, `projects`, `agents`, `health_events`, `message_deliveries`.
   - `docker compose ... down`.
5. Qualquer outra entrada → **preserva** DB/Redis.
6. `start.sh` ao final (religa tudo).

### ⚠️ Alto impacto

O caminho `CONFIRMO` **apaga dados de orquestração** (tarefas, projetos, agentes, mensagens, custos por schema `aop_*`). **Sempre** faça backup antes ([`22-BACKUP-RESTORE.md`](22-BACKUP-RESTORE.md)).

```bash
# Backup antes de qualquer flush destrutivo:
BACKUP_ROOT=/mnt/c/VMs/Projects/AOP/deploy/backups bash AOP/ops/db-backup.sh full
bash AOP/ops/flush-restart.sh
# Digite CONFIRMO somente se realmente quer apagar.
```

---

## 3. Outros utilitários de ops

| Script | Função (verificada) | Observação |
|--------|----------------------|------------|
| `ops/agent-registry-reconcile.sh` | reconcilia o registry de agentes | revisar antes de rodar; não auditado nesta entrega |
| `ops/sync_agent_identity.py` | sincroniza identidade de agentes (login copiado do Herdr) | relacionado ao reaproveitamento de login do Herdr |
| `ops/install-backup-cron.sh` | agenda cron: hourly :05, full domingo 03:00 | ⚠️ não exporta `BACKUP_ROOT` → herda o default obsoleto; corrigir (ver doc 22) |

> `agent-registry-reconcile.sh` e `sync_agent_identity.py` **não foram auditados em profundidade** nesta entrega de documentação. A squad deve lê-los antes de executar e documentar o comportamento observado.

### Verificação do cron instalado

```bash
crontab -l | sed -n '/AOP db-backup (managed)/,/<<< AOP db-backup/p'
```

# 🛠️ OPS Runbook — HerdMaster
**Versão:** 2026-06-25T16:17Z | Mantido por: Operador + Antigravity (Tech Lead Support)

> [!IMPORTANT]
> Todos os comandos requerem autorização explícita por escrito do operador antes de execução.
> Nenhum agente deve executar comandos neste runbook de forma autônoma sem aprovação prévia.

---

## 1. Comandos de Gestão do Stack

### Script principal
```bash
/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/ops/bootstrap.sh <acao>
```

### Aliases instalados em `~/.bashrc` (requer shell interativo `-i`)

| Alias | Comando equivalente | Descrição |
|-------|-------------------|-----------|
| `hm-status` | `bootstrap.sh status` | Estado completo de todos os componentes (sem alterar nada) |
| `hm-start` | `bootstrap.sh start` | Inicia o Control Plane |
| `hm-stop` | `bootstrap.sh stop` | Para o Control Plane (preserva tudo) |
| `hm-restart` | `bootstrap.sh restart` | Restart SEM apagar dados ou logs |
| `hm-reset` | `bootstrap.sh reset-soft` | Limpa prompts residuais/sockets, preserva DB |
| `hm-agents` | `bootstrap.sh agents-flush` | Envia `/chat new` para todos os agentes (limpa contexto) |
| `hm-flush` | `bootstrap.sh reset-hard` | **FLUSH TOTAL** — apaga DB+prompts (pede `CONFIRMO`) |
| `hm-help` | `bootstrap.sh` | Exibe menu completo |

---

## 2. Detalhamento de Cada Ação

### `hm-start` — Bootstrap / Iniciar

**O que faz (em ordem):**
1. Verifica se HerdMaster já está rodando (evita duplicação)
2. Inicia processo `herdmaster start --http` em background (`nohup`)
3. Aguarda até 15s confirmando PID e socket ativos
4. ✅ Sistema pronto

**Preserva:** tudo (DB, projetos, tasks, logs, agentes)

---

### `hm-stop` — Parar de forma ordenada

**O que faz:**
1. Lê PID de `herdmaster.pid`
2. Envia `SIGTERM` → aguarda 10s shutdown gracioso
3. Se necessário: força `SIGKILL`
4. Remove sockets e PID file

**Preserva:** DB, tasks, logs, configuração
**Remove:** sockets temporários (`herdmaster.sock`, `herdmaster-api.sock`, `herdmaster.pid`)

---

### `hm-restart` — Restart preservando tudo

**O que faz:** `stop` + 2s + `start`

**Preserva:** **TUDO** — DB, projetos, tasks, logs, histórico, contexto dos agentes

> Use este comando após `wsl --shutdown`. O DB e logs ficam 100% intactos.

---

### `hm-reset` — Reset Soft

**O que apaga:** prompt files residuais (`task-*.md`), sockets stale
**O que preserva:** DB, tasks, projetos, histórico, config.toml
**Confirmação:** pede `[s/N]`

---

### `hm-flush` — Flush Total (IRREVERSÍVEL)

**O que apaga:** DB inteiro (`herdmaster.db`, WAL, SHM), todos os prompts, sockets
**O que preserva:** `config.toml`, processos Herdr, panes dos agentes
**Confirmação:** você deve digitar `CONFIRMO` para prosseguir

> [!CAUTION]
> Após `hm-flush`, o sistema inicia do zero. Todos os projetos, tasks e histórico são perdidos
> permanentemente. Use apenas quando necessário reiniciar completamente o pipeline.

---

## 3. Flush Manual via SQLite (Alternativa ao hm-flush)

Use quando quiser preservar os agentes mas limpar apenas tasks/projetos sem parar o HerdMaster:

```bash
DB="/home/dataops-lab/.config/herdmaster/herdmaster.db"

# Limpar tasks e projetos (preserva agentes e configuração)
sqlite3 "$DB" "DELETE FROM tasks;"
sqlite3 "$DB" "DELETE FROM projects;"
sqlite3 "$DB" "DELETE FROM project_history;"
sqlite3 "$DB" "DELETE FROM task_audit_log;"
sqlite3 "$DB" "DELETE FROM messages;"
sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 "$DB" "VACUUM;"

# Verificar resultado
sqlite3 "$DB" "SELECT COUNT(*) || ' tasks' FROM tasks; SELECT COUNT(*) || ' projects' FROM projects; SELECT COUNT(*) || ' agents' FROM agents;"
```

---

## 4. Corrigir Labels de Agentes no DB

```bash
DB="/home/dataops-lab/.config/herdmaster/herdmaster.db"

# Atualizar label de um agente
sqlite3 "$DB" "UPDATE agents SET label='NOVO_LABEL', updated_at=datetime('now') WHERE id='w8:p1';"

# Verificar todos os agentes
sqlite3 "$DB" "SELECT id, label, type, role FROM agents ORDER BY id;"
```

---

## 5. Corrigir Roles de Agentes

> [!IMPORTANT]
> `role=orchestrator` → nunca recebe tasks (filtrado pelo SquadRecommender)
> `role=worker` → recebe e executa tasks via prompt injection

```bash
DB="/home/dataops-lab/.config/herdmaster/herdmaster.db"

# Promover agente para orchestrator (ex: Kiro)
sqlite3 "$DB" "UPDATE agents SET role='orchestrator', updated_at=datetime('now') WHERE id='w6:p7';"

# Rebaixar para worker (se necessário)
sqlite3 "$DB" "UPDATE agents SET role='worker', updated_at=datetime('now') WHERE id='w6:p8';"
```

**Roles atuais corretos (pós 2026-06-25T16:17Z):**
- `orchestrator`: `cli` (CLI Operator), `w6:p7` (Kiro_Opus-48)
- `worker`: `w6:p1` AGY_Opus-46, `w6:p2` AGY_Gemini_PRO-31, `w6:p5` Codex_#1, `w6:p6` Codex_#2, `w6:p8` AGY_Flash35-High-Thinking

> [!NOTE]
> O allowlist guard em `watchdog/engine.py` garante que apenas estes 7 agentes existem no DB.
> Ver [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) para o procedimento de adicionar um novo agente.

---

## 6. Diagnosticar Problema de Task com Falha

### Erro: `"agent 'X' has no resolvable Herdr pane"`

**Causa:** Task foi atribuída a um agente que:
- Tem `role=orchestrator` (nunca deveria receber tasks), OU
- Tem `herdr_pane=NULL` e é um worker (pane não registrado no Herdr)

**Diagnóstico:**
```bash
DB="/home/dataops-lab/.config/herdmaster/herdmaster.db"
# Verificar role e pane do agente
sqlite3 "$DB" "SELECT id, label, role, herdr_pane FROM agents WHERE id='AGENT_ID';"

# Verificar tasks failed
/home/dataops-lab/.local/bin/herdmaster tasks list --state failed --json
```

**Solução A — Agente é orchestrator (ex: cli/Kiro) atribuído por engano:**
```bash
# Não reatribuir — o orchestrator não pode ter pane. Recriar a task para um worker:
/home/dataops-lab/.local/bin/herdmaster tasks create --title "..." --prompt "..." --assigned_to w6:p1
```

**Solução B — Worker legítimo mas pane não registrado:**
```bash
# Verificar se o pane existe no Herdr
/home/dataops-lab/.local/bin/herdr pane list
# Re-registrar pane no DB
sqlite3 "$DB" "UPDATE agents SET herdr_pane='w6:p1', updated_at=datetime('now') WHERE id='AGENT_ID';"
```

---

## 7. Checklist de Saúde do Sistema

Execute `hm-status` e verifique:

```
✅ HerdMaster RUNNING (PID=XXX)
✅ Socket EXISTS: herdmaster.sock
✅ Socket EXISTS: herdmaster-api.sock
✅ Herdr RUNNING (PID=XXX)
✅ DB EXISTS (tamanho razoável, WAL próximo de 0)
   Task counts: (idealmente 0 failed, sem tasks stuck em running por horas)
✅ Agentes: todos idle/healthy com herdr_pane correto
✅ Prompt files residuais: 0
```

**Alertas que requerem ação:**

| Sinal | Ação |
|-------|------|
| WAL > 10MB | `sqlite3 $DB 'PRAGMA wal_checkpoint(TRUNCATE);'` |
| Prompts residuais > 0 | `rm ~/.config/herdmaster/prompts/task-*.md` |
| Agente `failed` tasks > 3 | Verificar `error_message` no DB; recriar tasks |
| HerdMaster NOT RUNNING | `hm-start` |
| Socket MISSING mas process alive | `hm-restart` |

---

## 9. Stack de Observabilidade

### Componentes e Portas

| Serviço | Porta | URL |
|---------|-------|-----|
| HerdMaster API + métricas | 8080 | `http://127.0.0.1:8080/metrics` |
| Prometheus | 9090 | `http://localhost:9090` |
| Alertmanager | 9093 | `http://localhost:9093` |
| Webhook Remediation | 9099 | `http://localhost:9099/health` |
| Grafana | 3000 | `http://localhost:3000` (admin/admin) |

### Iniciar/Parar Stack de Observabilidade

```bash
cd /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability

# Iniciar todos os containers
docker compose up -d

# Verificar status
docker compose ps

# Ver logs do webhook de remediação
docker logs herdmaster-remediation --tail 20

# Parar tudo (preserva dados)
docker compose down
```

### Testar Loop E2E (Ghost → Alert → Purge)

```bash
bash /mnt/c/Users/dataops-lab/.gemini/antigravity-ide/brain/c4b28648-62a0-4c80-82f1-4df9bfddae95/scratch/e2e_alert_test.sh
```

O teste leva ~45s e valida:
1. Injeção de agente fantasma via SQLite
2. Detecção pelo Prometheus (10s)
3. Alert FIRING no Alertmanager (25s)
4. Purga via HTTP API pelo webhook (45s)
5. Retorno a `unlisted=0, compliant=1`

### Cheklist de Saúde da Observabilidade

```bash
# Métricas atuais
curl -s http://127.0.0.1:8080/metrics | grep herdmaster_

# Queries essenciais no Prometheus (http://localhost:9090/graph)
# herdmaster_whitelist_compliant     → deve ser 1
# herdmaster_unlisted_agents_total   → deve ser 0
# herdmaster_agents_total            → deve ser 7

# Estado dos alertas
curl -s http://localhost:9093/api/v2/alerts | python3 -m json.tool

# Health do webhook
curl -s http://localhost:9099/health | python3 -m json.tool
```

---

## 10. Workflow de Desenvolvimento (Pipx Editable)

O HerdMaster está instalado em modo editável desde 2026-06-25:

```bash
# Verificar que o install é editable
cat ~/.local/share/pipx/venvs/herdmaster/lib/python3.12/site-packages/__editable__.herdmaster-1.0.0.pth
# → /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/src
```

**Impacto:** qualquer mudança no source em `HerdMaster/src/herdmaster/` está **imediatamente ativa** após restart do processo — sem `cp`, sem reinstall.

### Ciclo de desenvolvimento padrão

```bash
# 1. Editar código fonte
vim /mnt/c/VMs/Projects/.../HerdMaster/src/herdmaster/watchdog/engine.py

# 2. Restart (aplica automaticamente)
hm-restart

# 3. Verificar
hm-status
curl -s http://127.0.0.1:8080/metrics | grep herdmaster_
```

### Se precisar reinstalar (ex: nova dependência em pyproject.toml)

```bash
pipx install --editable --force /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster
```

### Se o DB ficar locked após um crash

```bash
# 1. Verificar se há processo segurando
fuser ~/.config/herdmaster/herdmaster.db

# 2. Checkpoint WAL
sqlite3 ~/.config/herdmaster/herdmaster.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 3. Limpar arquivos WAL residuais
rm -f ~/.config/herdmaster/herdmaster.db-wal ~/.config/herdmaster/herdmaster.db-shm

# 4. Restart limpo
hm-restart
```

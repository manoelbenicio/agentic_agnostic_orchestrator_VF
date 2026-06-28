# 21 — Subir e Derrubar o Stack

Origem da verdade: `ops/start.sh`, `ops/stop.sh`, `ops/common.sh`.

## 1. Subir tudo

```bash
bash AOP/ops/start.sh
```

### Sequência exata (de `start.sh`)

1. **Pré-checagem:** `require_cmd docker curl lsof ss npm setsid` + `load_aop_env` (carrega `.env`, monta `DATABASE_URL`/`REDIS_URL`).
2. **Base:** `docker compose ... up -d` →
   - `wait_until "postgres" 60 2 ... pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`
   - `wait_until "redis" 60 2 ... redis-cli ping`
3. **Observabilidade:** `write_prometheus_token` → `docker compose -f ../HerdMaster/deploy/observability/... up -d` → espera HTTP 200 em:
   - Prometheus `:9090/-/healthy`, Grafana `:3000/api/health`, Alertmanager `:9093/-/ready`, Blackbox `:9115/-/healthy`, Remediation `:9099/health`.
4. **HerdMaster:** `write_herdmaster_config` → se `:8080/metrics` já responde 200 (com Bearer), reaproveita; senão `kill_port_processes` + `setsid herdmaster start --http --config <toml>` e espera `:8080/metrics`.
5. **Control-plane:** se `:8090/health` == 200 **e** `coupling.status == connected`, reaproveita; senão `setsid uvicorn app.main:app --host 127.0.0.1 --port 8090` (com `DATABASE_URL`, `REDIS_URL`, `HERDMASTER_URL`, `HERDMASTER_TOKEN`, `PYTHONPATH`) e espera `/health` + `/health/ready`.
6. **Frontend:** se `:13000` == 200, reaproveita; senão `setsid npm run dev -- --hostname 127.0.0.1 --port 13000` (com `NEXT_PUBLIC_API_URL`).
7. **`print_status_table`** — tabela final com status de cada componente.

> **Idempotência:** cada serviço de aplicação só sobe se ainda não estiver saudável. Rodar `start.sh` duas vezes não duplica processos. PIDs ficam em `/tmp/aop-ops-run/*.pid`.

### Logs

Cada serviço de host loga em `ops/logs/`:
- `ops/logs/herdmaster.log`
- `ops/logs/aop-control-plane.log`
- `ops/logs/aop-frontend.log`

```bash
tail -f AOP/ops/logs/aop-control-plane.log
tail -f AOP/ops/logs/aop-frontend.log
```

---

## 2. Derrubar tudo

```bash
bash AOP/ops/stop.sh
```

### Sequência exata (de `stop.sh`)

1. `stop_pid_file` + `kill_port_processes` para **frontend** (:13000).
2. idem para **control-plane** (:8090).
3. idem para **HerdMaster** (:8080) + remove `herdmaster.sock`/`herdmaster.pid` do runtime.
4. `docker compose -f <observability> down` (remove containers de observabilidade).
5. `docker compose ... stop postgres redis` — **stop, não down**: preserva rede, volume e dados.
6. `print_status_table`.

> **Diferença crítica:** `stop.sh` **preserva** o volume `aop_postgres_data`. Para reset destrutivo use `flush-restart.sh` (ver [`25-STATUS360-E-DASHBOARD.md`](25-STATUS360-E-DASHBOARD.md)).

---

## 3. Gestão de processos de host

`common.sh` gerencia processos de longa duração via **process groups** (`setsid` no start, `kill -TERM -- -PID` no stop):

- `stop_pid_file` envia `SIGTERM` ao grupo, espera até 20s, escala para `SIGKILL` se necessário.
- `kill_port_processes` mata listeners "órfãos" na porta (via `lsof`/`fuser`) que não foram registrados em PID file.
- `record_listener_pid` grava o PID real do listener após subir.

### Verificação de processos

```bash
ls -1 /tmp/aop-ops-run/*.pid 2>/dev/null
for f in /tmp/aop-ops-run/*.pid; do
  pid="$(tr -dc '0-9' < "$f")"; echo "$f -> pid=$pid $(kill -0 "$pid" 2>/dev/null && echo VIVO || echo MORTO)"
done
```

---

## 4. Reinício seletivo

Não há script dedicado por serviço, mas como `start.sh` é idempotente:

```bash
# Reiniciar só o control-plane:
bash AOP/ops/stop.sh            # derruba tudo (limpo)
bash AOP/ops/start.sh           # sobe tudo de novo

# Reaproveitamento: se você matar só o uvicorn (kill do PID em aop-control-plane.pid)
# e rodar start.sh, ele detecta que :8090 está down e religa apenas o control-plane.
```

> Para reinício fino (um único serviço sem derrubar os demais), a recomendação é matar o PID específico e rodar `start.sh` — a idempotência religa só o que caiu. Um script `restart-<svc>.sh` dedicado **não existe** hoje (possível melhoria, ver `24-RUNBOOK-INCIDENTES.md`).

---

## 5. Tabela de status sob demanda

`print_status_table` (em `common.sh`) é chamada ao fim de `start.sh` e `stop.sh`. Ela consulta:
- `port_listening 5432/6379` (via `ss`)
- `http_code` de Prometheus/Grafana/Alertmanager/Blackbox/Remediação/HerdMaster/API/Frontend.

Para vê-la isolada sem reiniciar, a forma suportada é re-executar `start.sh` (idempotente) — ele imprime a tabela ao final sem religar o que já está de pé.

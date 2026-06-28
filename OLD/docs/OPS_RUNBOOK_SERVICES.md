# Ops Runbook — Services, Startup Sequence, Restarts & Behaviors

Documentação operacional do stack AOP + HerdMaster + Observabilidade, com a **sequência de
componentes**, **procedimentos de restart** e **comportamentos observados** em runtime.
Capturado ao vivo em 2026-06-26 (a pedido do operador). Estado verificado via `docker ps`,
`ss -ltnp`, pid files e os arquivos de compose/ops.

---

## 1. Inventário de serviços (estado verificado)

| Componente | Tipo | Porta (bind) | Rede | DB/estado | Gerenciado por |
|---|---|---|---|---|---|
| **deploy-postgres-1** | container (pgvector/pgvector:pg17) | 127.0.0.1:5432 | `deploy_aop_net` (bridge) | DB `aop` (TODOS os schemas canônicos) | `AOP/deploy/docker-compose.yml` |
| **deploy-redis-1** | container (redis:7-alpine) | 127.0.0.1:6379 | `deploy_aop_net` | cache/bus | `AOP/deploy/docker-compose.yml` |
| **herdmaster** (control plane) | processo host (pipx editable) | 127.0.0.1:8080 | host | usa deploy-postgres `aop`, schema `hm_main` | `AOP/ops/start.sh` → pid `/tmp/aop-ops-run/herdmaster.pid` |
| **AOP control-plane** | processo host (uvicorn) | 127.0.0.1:8090 | host | usa deploy-postgres `aop`, schemas `aop_*` | `AOP/ops/start.sh` → `aop-control-plane.pid` |
| **AOP frontend** | processo host (next-server) | 127.0.0.1:13000 | host | — | `AOP/ops/start.sh` → `aop-frontend.pid` |
| **herdmaster-prometheus** | container | *:9090 | **host** | scrape | `HerdMaster/deploy/observability/docker-compose.yml` |
| **herdmaster-grafana** | container | *:3000 | **host** | dashboards provisionados | obs compose |
| **herdmaster-alertmanager** | container | *:9093 | **host** | rotas de alerta | obs compose |
| **herdmaster-blackbox** | container | *:9115 | **host** | probes | obs compose |
| **herdmaster-remediation** | container (python:3.12-slim) | 127.0.0.1:9099 | **host** | auto-purge anti-ghost | obs compose |
| **herdmaster-postgres** | container (postgres:16) | — (sem porta publicada) | bridge | **ÓRFÃO/legado** — o stack AOP NÃO usa este; usa deploy-postgres-1 | (deploy standalone antigo do HerdMaster) |

> ⚠️ Comportamento/oddity: existem **dois** Postgres. O canônico é `deploy-postgres-1` (pg17, :5432).
> `herdmaster-postgres` (pg16, bridge, sem porta) é legado e não participa do fluxo atual.
> Candidato a remoção futura (registrar em backlog antes de qualquer ação).

## 2. Sequência de boot (ordem de dependência)

```
1. deploy-postgres-1   (DB)      ─┐  base de dados — tudo depende
2. deploy-redis-1      (cache)    │  (AOP/ops/start.sh sobe 1+2 via docker compose)
3. herdmaster :8080    (control)  │  precisa do DB pronto (init_db idempotente no boot)
4. AOP control-plane :8090        │  precisa do DB + token do herdmaster (coupling)
5. AOP frontend :13000            │  consome a API :8090
6. Observabilidade (obs compose): │
   6a. prometheus :9090           │  scrapeia 8080/8090/9099/9115
   6b. blackbox :9115             │
   6c. alertmanager :9093         │
   6d. grafana :3000              │  datasource = prometheus
   6e. remediation :9099  ────────┘  depends_on: alertmanager (recebe webhook de alerta)
```
- Boot único do stack: `bash AOP/ops/start.sh` (sobe DB/Redis/obs/herdmaster/control-plane/frontend).
- Encerrar: `bash AOP/ops/stop.sh` (NÃO toca no Herdr/multiplexer).

## 3. Comportamentos observados (importantes)

- **start.sh é idempotente / "skip-if-healthy"**: se `http://127.0.0.1:8080/metrics` já responde 200,
  ele loga "already healthy" e **NÃO reinicia** o herdmaster. ⇒ start.sh **não** recarrega código novo;
  para recarregar é preciso restart explícito (ver §4.1).
- **herdmaster é pipx *editable*** (`herdmaster.__file__` aponta para `HerdMaster/src/herdmaster`).
  Editar o source só tem efeito **após restart do processo** (o módulo é importado no boot).
- **Watchdog re-sincroniza agentes do herdr**: no boot/poll (poll_interval_s=15), o herdmaster
  ingere os panes do `herdr pane list`. Com `agent_allowlist` vazio (config atual) ele aceita todos —
  por isso, após um flush, os panes voltam a aparecer (re-registro). Não introduz ghosts pois só
  existem os panes reais (w8:*).
- **Auto-purge anti-ghost (remediation)**: Prometheus detecta `herdmaster_unlisted_agents_total > 0`
  → Alertmanager FIRING → `POST :9099/webhook/remediate` → `purge_unlisted_agents()` deleta via
  `DELETE /agents/{id}` quem estiver fora da whitelist. Hot-reload: relê a whitelist do arquivo a
  cada chamada.
- **Whitelist agora é dinâmica** (fonte única): `~/.config/herdmaster/agent_whitelist.json`,
  reescrita de hora em hora pelo reconciliador a partir do roster vivo. Lida por `server.py`
  (exporter) e `webhook_server.py` (purge). Montada no container em `/herdmaster-data/`.
- **WSL2 + host-network**: containers obs (`network_mode: host`) escutam em `*:PORTA` na VM WSL.
  O WSL2 NÃO encaminha essas portas ao `localhost` do Windows ⇒ do browser Windows usar o IP do
  WSL (`172.19.77.147:3000/9090/9093`). Esse IP muda a cada reboot do WSL.
- **FK rules em `hm_main.agents`**: `health_events`→CASCADE; `messages/task_alerts/task_audit_log/
  tasks`→SET NULL. ⇒ deletar/prune de agente é seguro (sem violação).
- **Cron persiste reboot**: `cron` habilitado no systemd (`systemctl is-enabled cron` = enabled).

## 4. Procedimentos de restart (com o que foi feito nesta sessão)

### 4.1 HerdMaster control plane (host, pipx editable) — restart fiel
Necessário sempre que `HerdMaster/src/**` muda (ex.: exporter de métricas).
```bash
TOKEN=$(cat /tmp/aop-ops-runtime/herdmaster.token)
kill "$(cat /tmp/aop-ops-run/herdmaster.pid)"           # TERM gracioso
# aguarde o processo sair (pgrep -f 'herdmaster start --http')
( cd HerdMaster
  setsid env DATABASE_URL="postgresql://aop_dev:aop_dev_postgres_20260626@127.0.0.1:5432/aop" \
             PYTHONPATH="$PWD/src" \
    herdmaster start --http --config /tmp/aop-ops-runtime/herdmaster.config.toml \
    >> ../AOP/ops/logs/herdmaster.log 2>&1 < /dev/null &
  echo $! > /tmp/aop-ops-run/herdmaster.pid )
# readiness:
curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/metrics  # espera 200
```
> Observado nesta sessão: pid 64431 → kill → relaunch → **pid 143328**, healthy(200) em 2 tentativas.
> Após o restart, métricas de integridade passaram a `expected=9, unlisted=0, compliant=1`.

### 4.2 Remediation webhook (container) — recreate p/ código/env novo
Necessário quando `webhook_server.py` ou env (`AGENT_WHITELIST_FILE`) muda.
```bash
docker compose -f HerdMaster/deploy/observability/docker-compose.yml up -d --force-recreate remediation-webhook
curl -s http://127.0.0.1:9099/metrics | grep whitelist_size     # espera 9
docker logs herdmaster-remediation | grep -i whitelist | tail -1
```
> Observado: container `Recreated/Started`; log `Whitelist (9 agents): [cli, w8:p12, ...]`.

### 4.3 Prometheus — reload sem restart (lifecycle habilitado)
Para aplicar mudança em `prometheus.yml`/`alert_rules.yml` sem derrubar TSDB:
```bash
curl -s -X POST http://127.0.0.1:9090/-/reload
curl -s 'http://127.0.0.1:9090/api/v1/targets?state=active'   # confira health dos targets
```
> Observado: reload OK; targets `herdmaster-internal-metrics`, `herdmaster-remediation`,
> `herdmaster-e2e-api-monitor` = **up**.

### 4.4 Grafana / Alertmanager / Blackbox (containers)
```bash
docker compose -f HerdMaster/deploy/observability/docker-compose.yml restart grafana       # dashboards/datasources são :ro provisionados; editar JSON no host + restart
docker compose -f HerdMaster/deploy/observability/docker-compose.yml restart alertmanager   # após mudar alertmanager.yml
```

### 4.5 AOP control-plane / frontend (host)
Gerenciados pelo start.sh; reinício direcionado:
```bash
kill "$(cat /tmp/aop-ops-run/aop-control-plane.pid)"   # e relançar via start.sh (sobe só o que não está healthy)
bash AOP/ops/start.sh
```

### 4.6 Backups & reconciliação (cron) — não são serviços long-running
- `AOP/ops/db-backup.sh full|hourly` (cron :05 horário / domingo 03:00).
- `AOP/ops/agent-registry-reconcile.sh [--flush]` (cron :15 horário).
- Verificar daemon: `pgrep -ax cron`; persistência: `systemctl is-enabled cron`.

## 5. Log cronológico de restarts desta sessão
| Hora (local) | Componente | Ação | Resultado verificado |
|---|---|---|---|
| ~20:51 | (nenhum restart) | db-backup full | dump 144K verificado (33 schemas) |
| ~20:56 | cron | install-backup-cron | hourly :05 + full dom 03:00 |
| ~21:17 | hm_main (DB) | flush+reseed (reconcile --flush) | 9 agents, ghost=0 |
| ~21:18 | **herdmaster** | kill 64431 → relaunch 143328 | healthy 200; integrity compliant=1 |
| ~21:20 | **remediation** | docker compose up -d --force-recreate | whitelist_size=9; log confirma roster w8 |
| ~21:20 | **prometheus** | POST /-/reload | targets up |

## 6. Estado final verificado
- Schemas: 11 canônicos + `public` (22 órfãos removidos, com backup prévio).
- Integridade: `herdmaster_whitelist_compliant=1`, `herdmaster_unlisted_agents_total=0`,
  `agents_total=expected_total=9`.
- Control-plane: `status:ok`, coupling `connected`.
- Cron: backup (hourly/weekly) + reconcile (hourly) instalados e persistentes.

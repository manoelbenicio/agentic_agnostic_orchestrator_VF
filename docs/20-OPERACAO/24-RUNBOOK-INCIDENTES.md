# 24 — Runbook de Incidentes

Procedimentos de diagnóstico e recuperação por componente. Todos os comandos são reproduzíveis; nenhum efeito de runtime foi fabricado.

## 0. Triagem rápida

```bash
# Visão geral (re-executa start.sh idempotente; imprime print_status_table ao fim):
bash AOP/ops/start.sh

# Portas em escuta:
ss -ltn | grep -E ':(5432|6379|8080|8090|13000|9090|3000|9093|9115|9099)\b'

# Logs recentes:
tail -n 50 AOP/ops/logs/aop-control-plane.log
tail -n 50 AOP/ops/logs/herdmaster.log
tail -n 50 AOP/ops/logs/aop-frontend.log
```

---

## 1. Control-plane não responde em :8090

**Sintomas:** `curl :8090/health` falha; tabela mostra AOP API ≠ 200.

```bash
tail -n 80 AOP/ops/logs/aop-control-plane.log     # stacktrace do uvicorn
/tmp/aop-control-plane-venv/bin/uvicorn --version  # venv intacta?
curl -s http://127.0.0.1:8090/health/ready         # checa PG/Redis
```

Causas comuns:
- **Venv ausente/quebrada** → recriar (ver [`10-DEPLOY/12-INSTALACAO.md`](../10-DEPLOY/12-INSTALACAO.md)).
- **Postgres/Redis down** → `/health/ready` retorna 503 com `checks`. Subir base.
- **PYTHONPATH sem HerdMaster** → `ImportError: herdmaster...`. Confirmar `PYTHONPATH` no `start.sh`.

Recuperação:
```bash
kill "$(tr -dc 0-9 </tmp/aop-ops-run/aop-control-plane.pid)" 2>/dev/null
bash AOP/ops/start.sh   # religa só o que caiu
```

---

## 2. Coupling "degraded" (HerdMaster)

**Sintomas:** `/health` retorna `coupling.status = "degraded"`.

`_coupling_health` (em `app/main.py`) reporta:
- `"HerdMaster token is not configured"` → `HERDMASTER_TOKEN` não chegou ao uvicorn.
- `"HerdMaster HTTP unavailable"` → probe autenticado falhou (HerdMaster down ou token errado).

```bash
# HerdMaster vivo e aceitando o token?
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $(tr -d '\r\n' </tmp/aop-ops-runtime/herdmaster.token)" \
  http://127.0.0.1:8080/metrics
tail -n 80 AOP/ops/logs/herdmaster.log
cat /tmp/aop-ops-runtime/herdmaster.config.toml | grep -A2 '\[api\]'
```

Recuperação: garantir token (`ensure_herdmaster_token`), reiniciar HerdMaster, depois control-plane (`stop.sh` + `start.sh`).

> Lembrete: sem HerdMaster, o socket-mode cai no **fallback gracioso** (ADR-001) — ver [`30-COMPONENTES/33-COUPLING-HERDMASTER-HERDR.md`](../30-COMPONENTES/33-COUPLING-HERDMASTER-HERDR.md).

---

## 3. Postgres / Redis indisponíveis

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps
docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs --tail=50 postgres
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T postgres \
  pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T redis redis-cli ping
```

Recuperação:
```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d postgres redis
```

> **Nunca** rode `down -v` em produção (apaga o volume `aop_postgres_data`). Restore só via `db-restore.sh` ([`22-BACKUP-RESTORE.md`](22-BACKUP-RESTORE.md)).

---

## 4. Porta ocupada por processo órfão

`start.sh` chama `kill_port_processes` antes de subir, mas se necessário manualmente:

```bash
lsof -tiTCP:8090 -sTCP:LISTEN     # quem está na porta
# matar listener órfão (cuidado!):
kill "$(lsof -tiTCP:8090 -sTCP:LISTEN | head -1)"
```

---

## 5. Frontend :13000 não sobe

```bash
tail -n 80 AOP/ops/logs/aop-frontend.log
( cd web && npm ci )      # dependências íntegras?
```

Causas: `node_modules` ausente, versão de Node incompatível com Next 16, porta ocupada.

---

## 6. Observabilidade não sobe

A stack está em `../HerdMaster/deploy/observability`. Se `start.sh` trava esperando Prometheus/Grafana:

```bash
docker compose -f ../HerdMaster/deploy/observability/docker-compose.yml ps
docker compose -f ../HerdMaster/deploy/observability/docker-compose.yml logs --tail=50
# Prometheus não autentica no HerdMaster? Token 644 sincronizado?
stat -c '%a %n' /tmp/aop-ops-runtime/prometheus.token
```

Recuperação: `write_prometheus_token` (rodar `start.sh` reescreve) + reiniciar Prometheus.

---

## 7. Reset total (último recurso, destrutivo)

Quando o estado está corrompido e backups estão a salvo:

```bash
bash AOP/ops/flush-restart.sh     # pede "CONFIRMO" para reset destrutivo
```

Ver detalhes e o que é apagado em [`25-STATUS360-E-DASHBOARD.md`](25-STATUS360-E-DASHBOARD.md). **Faça backup antes** ([`22-BACKUP-RESTORE.md`](22-BACKUP-RESTORE.md)).

---

## 8. Matriz de escalonamento (sugerida)

| Severidade | Exemplo | Ação |
|-----------|---------|------|
| SEV-1 | Postgres down / perda de dados | restore + RCA; congelar squad |
| SEV-2 | control-plane down, coupling degradado | runbook §1/§2; notificar TL |
| SEV-3 | frontend/observabilidade down | runbook §5/§6 |
| SEV-4 | warning isolado | registrar e seguir |

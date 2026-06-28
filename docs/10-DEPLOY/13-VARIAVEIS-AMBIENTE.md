# 13 — Variáveis de ambiente

## 1. Arquivo `.env` (base do compose)

Origem: `deploy/.env.example` → copiar para `deploy/.env`. Carregado por `common.sh::load_aop_env` com `set -a; source ...; set +a`.

| Variável            | Exemplo (template)              | Uso |
|---------------------|---------------------------------|-----|
| `POSTGRES_USER`     | `aop_dev`                       | usuário do Postgres (compose + `DATABASE_URL`) |
| `POSTGRES_PASSWORD` | `change-me-postgres-password`   | senha do Postgres |
| `POSTGRES_DB`       | `aop`                           | database padrão |
| `REDIS_PASSWORD`    | `change-me-redis-password`      | senha do Redis |

> **Validação obrigatória (`load_aop_env`):** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` e `REDIS_PASSWORD` precisam existir, senão o boot aborta com erro.

---

## 2. Variáveis derivadas (geradas em runtime)

`load_aop_env` exporta, a partir do `.env`:

```bash
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
export REDIS_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0"
```

---

## 3. Variáveis injetadas no control-plane

`start.sh` injeta no processo uvicorn:

```bash
DATABASE_URL="${DATABASE_URL}"
REDIS_URL="${REDIS_URL}"
HERDMASTER_URL="http://127.0.0.1:8080"
HERDMASTER_TOKEN="$(herdmaster_token)"
PYTHONPATH="${AOP_DIR}/control-plane:${HERDMASTER_DIR}/src"
```

O control-plane lê configuração via `Settings.from_env()` (`app/settings.py`). Variáveis relevantes observadas no código (`app/main.py`):

| Variável            | Efeito |
|---------------------|--------|
| `DATABASE_URL`      | conexões Postgres (`state.postgres_connections`, `/health/ready`) |
| `REDIS_URL`         | cliente Redis (`state.redis_client`, `/health/ready`) |
| `HERDMASTER_URL`    | base do message bus / probes de coupling |
| `HERDMASTER_TOKEN`  | Bearer para o HerdMaster; **sem token → coupling fica `degraded`** (`_coupling_health`) |
| `CORS` origins      | `effective_settings.cors_origins` no middleware CORS |

> Comportamento verificado em `_coupling_health`: se `state.settings.herdmaster_token` for vazio, o `/health` retorna `coupling.status = "degraded"` com `last_error = "HerdMaster token is not configured"`.

---

## 4. Variáveis do frontend

`start.sh` sobe o Next com:

```bash
NEXT_PUBLIC_API_URL="http://127.0.0.1:8090" npm run dev -- --hostname 127.0.0.1 --port 13000
```

`NEXT_PUBLIC_API_URL` aponta o frontend para o control-plane. Por ser `NEXT_PUBLIC_*`, é embutida no bundle (cliente).

---

## 5. Variáveis de override de caminhos de runtime

`common.sh` aceita overrides (úteis para isolar ambientes — ver governança de squad):

| Variável                 | Default            | Efeito |
|--------------------------|--------------------|--------|
| `AOP_OPS_RUN_DIR`        | `/tmp/aop-ops-run` | onde ficam os PID files |
| `AOP_OPS_RUNTIME_DIR`    | `/tmp/aop-ops-runtime` | token, config TOML, sockets |

`db-backup.sh` / `db-restore.sh` aceitam: `PG_CONTAINER` (default `deploy-postgres-1`), `PG_USER` (`aop_dev`), `PG_DB` (`aop`), `BACKUP_ROOT`, `RETAIN_FULL` (8), `RETAIN_HOURLY` (48).

> ⚠️ **`BACKUP_ROOT` tem default obsoleto** apontando para `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/AOP/deploy/backups` — caminho que **não corresponde** à raiz atual (`/mnt/c/VMs/Projects/AOP`). Ver [`20-OPERACAO/22-BACKUP-RESTORE.md`](../20-OPERACAO/22-BACKUP-RESTORE.md).

### Verificação

```bash
# Confirma que as derivadas são montadas corretamente (sem expor senha):
set -a; source deploy/.env; set +a
echo "DB host/db: 127.0.0.1:5432/${POSTGRES_DB} user=${POSTGRES_USER}"
echo "REDIS_URL seria: redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0"
```

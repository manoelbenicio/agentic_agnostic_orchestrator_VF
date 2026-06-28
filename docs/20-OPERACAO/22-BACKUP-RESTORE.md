# 22 — Backup e Restore

Origem da verdade: `ops/db-backup.sh`, `ops/db-restore.sh`, `ops/install-backup-cron.sh`.

## 1. Modelo de backup

`db-backup.sh` opera em dois modos sobre o Postgres (via `docker exec` no container):

| Modo | Frequência sugerida | Conteúdo | Retenção (default) |
|------|---------------------|----------|--------------------|
| `full` | semanal | `pg_dumpall --globals-only` (roles) + `pg_dump -Fc` completo | `RETAIN_FULL=8` (~2 meses) |
| `hourly` | de hora em hora | `pg_dump -Fc` autossuficiente (restaurável sozinho) | `RETAIN_HOURLY=48` (~2 dias) |

- Formato **custom** (`-Fc`): compacto e permite restore seletivo.
- Flags: `--no-owner --no-privileges`.
- **Toda dump é verificada** com `pg_restore --list` antes de ser mantida (`verify_dump`). Se a verificação falhar, o script aborta com `die`.
- Prune por retenção via `ls -1t ... | tail -n +N`.

### Estrutura de diretórios de backup

```
${BACKUP_ROOT}/
├── full/      aop_full_<TS>.dump
├── hourly/    aop_hourly_<TS>.dump
├── globals/   globals_<TS>.sql
└── backup.log
```

`<TS>` = `date -u +%Y%m%dT%H%M%SZ`.

---

## 2. Caminho de backup

O default atual resolve `BACKUP_ROOT` a partir da raiz real do checkout:

```bash
BACKUP_ROOT="${BACKUP_ROOT:-${AOP_DIR}/deploy/backups}"
```

O instalador de cron também grava `BACKUP_ROOT` explicitamente no bloco gerenciado, para evitar drift quando o repositório muda de diretório.

```bash
export BACKUP_ROOT="/mnt/c/VMs/Projects/AOP/deploy/backups"
```

---

## 3. Executar backup

```bash
# Snapshot horário (default se sem argumento):
BACKUP_ROOT=/mnt/c/VMs/Projects/AOP/deploy/backups bash AOP/ops/db-backup.sh hourly

# Backup completo semanal (globals + full):
BACKUP_ROOT=/mnt/c/VMs/Projects/AOP/deploy/backups bash AOP/ops/db-backup.sh full
```

Variáveis aceitas: `PG_CONTAINER` (default `deploy-postgres-1`), `PG_USER` (`aop_dev`), `PG_DB` (`aop`), `BACKUP_ROOT`, `RETAIN_FULL`, `RETAIN_HOURLY`.

> Pré-condição: container `deploy-postgres-1` rodando (`docker inspect -f '{{.State.Running}}'`); senão `die "container ... is not running"`.

### Verificação

```bash
ls -lt /mnt/c/VMs/Projects/AOP/deploy/backups/hourly/ | head
tail -n 5 /mnt/c/VMs/Projects/AOP/deploy/backups/backup.log
# Conferir integridade manual de um dump:
docker exec -i deploy-postgres-1 pg_restore --list \
  < /mnt/c/VMs/Projects/AOP/deploy/backups/hourly/<arquivo>.dump | head
```

---

## 4. Restore

```bash
bash AOP/ops/db-restore.sh <caminho-para-.dump> [target_db]
# target_db default = aop
```

Comportamento (de `db-restore.sh`):
1. Valida o arquivo (`-s` não vazio) e integridade (`pg_restore --list`).
2. `pg_restore -U $PG_USER -d $TARGET_DB --clean --if-exists --no-owner --no-privileges`.

> ⚠️ **`--clean --if-exists`**: objetos existentes são **dropados e recriados**. Restaurar sobre um banco com dados é destrutivo para os objetos coincidentes. Operação de alto impacto — confirmar antes em produção.

### Verificação pós-restore

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d aop -c "\dt"
```

---

## 5. Agendamento via cron

`ops/install-backup-cron.sh` instala as entradas de cron (full semanal + hourly). Inspecione o script antes de instalar:

```bash
cat AOP/ops/install-backup-cron.sh        # revisar o que será agendado
bash AOP/ops/install-backup-cron.sh       # instala (revisar BACKUP_ROOT antes!)
crontab -l | grep db-backup               # confirmar entradas
```

> **Atenção:** confirme que o bloco gerenciado aponta para a raiz atual e não para um checkout antigo.

---

## 6. Política recomendada (premium)

- **3-2-1:** manter cópias horárias locais + full semanal + replicar o `BACKUP_ROOT` para storage externo (S3/MinIO) fora do host.
- **Teste de restore mensal** em banco descartável (`db-restore.sh dump aop_restore_test`).
- **Monitorar `backup.log`** e alertar em falha de `verify_dump` (integração futura com Alertmanager).

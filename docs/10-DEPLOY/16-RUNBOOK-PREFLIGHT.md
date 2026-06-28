# 16 — Runbook de Pre-flight Consolidado

> **Objetivo:** checklist único, runnable e em sequência, que reúne todas as
> verificações dispersas em [`11-PRE-REQUISITOS.md`](11-PRE-REQUISITOS.md) a
> [`15-COMPOSE-E-SERVICOS.md`](15-COMPOSE-E-SERVICOS.md) e nos scripts
> `ops/common.sh`, `ops/start.sh`, `ops/stop.sh` e `ops/status360.py`.
>
> Executar os Passos 1–7 **antes** de `ops/start.sh` para garantir que o
> ambiente está pronto; os Passos 8–10 **após** a subida para confirmar
> que todos os serviços estão saudáveis.
>
> **Política de portas:** O control-plane (nativa **:8090**) e o frontend (nativa **:13000**),
> assim como os demais serviços (Postgres, Redis, HerdMaster e observabilidade),
> **sofrem deslocamento +5** se as portas estiverem ocupadas, conforme a política
> descrita no Passo 6. É necessário verificar a porta resolvida final ao efetuar healthchecks.
>
> **CWD assumido:** raiz do repositório AOP (`<ROOT>/AOP`).

---

## Pré-flight (executar antes de `ops/start.sh`)

### Passo 1 — Binários obrigatórios

`ops/start.sh` chama `require_cmd` para cada binário abaixo e aborta
imediatamente se algum faltar. `ops/flush-restart.sh` exige `find`;
`ops/common.sh` usa `openssl` (com fallback `sha256sum`) para gerar o token.

☐ **Verificar todos os binários:**

```bash
for c in docker curl lsof ss npm setsid find openssl; do
  command -v "$c" >/dev/null 2>&1 && echo "OK   $c" || echo "FALTA $c"
done
```

✅ **Pass:** todas as linhas mostram `OK`.
❌ **Fail:** alguma linha mostra `FALTA` → instale o binário antes de continuar.

| Binário    | Usado por                                              | Origem                             |
|------------|--------------------------------------------------------|------------------------------------|
| `docker`   | `start.sh`, `stop.sh`, `db-backup/restore.sh`          | compose base + observabilidade     |
| `curl`     | `common.sh` (`http_code`, `wait_http_200`)             | healthchecks HTTP                  |
| `lsof`     | `common.sh` (`record_listener_pid`, `kill_port_processes`) | descobrir PID por porta        |
| `ss`       | `common.sh` (`port_listening`)                         | checar portas em escuta            |
| `npm`      | `start.sh`                                             | rodar o frontend (`npm run dev`)   |
| `setsid`   | `start.sh`                                             | desacoplar processos (process group) |
| `find`     | `flush-restart.sh`                                     | limpeza de caches                   |
| `openssl`  | `common.sh` (`ensure_herdmaster_token`)                | gerar token (fallback: `sha256sum`) |

> **Referência:** [`11-PRE-REQUISITOS.md`](11-PRE-REQUISITOS.md) §2.

---

### Passo 2 — Layout irmão AOP + HerdMaster

A AOP exige o HerdMaster como projeto **irmão** no mesmo diretório-pai.
`ops/common.sh` deriva:

```bash
ROOT_DIR="$(cd "${AOP_DIR}/.." && pwd)"
HERDMASTER_DIR="${ROOT_DIR}/HerdMaster"
OBS_DIR="${HERDMASTER_DIR}/deploy/observability"
```

Se o HerdMaster não estiver em `../HerdMaster`, `start.sh` falha ao subir
a observabilidade e o HerdMaster.

☐ **Verificar layout:**

```bash
test -d "$(pwd)/../HerdMaster" \
  && echo "OK   HerdMaster irmão em ../HerdMaster" \
  || echo "FALTA HerdMaster irmão em ../HerdMaster"

test -f "$(pwd)/../HerdMaster/deploy/observability/docker-compose.yml" \
  && echo "OK   observability compose" \
  || echo "FALTA observability compose"
```

✅ **Pass:** ambas as linhas mostram `OK`.
❌ **Fail:** copie o HerdMaster para `../HerdMaster` (**cópia, não symlink** —
symlink escreveria de volta no original). Ver
[`11-PRE-REQUISITOS.md`](11-PRE-REQUISITOS.md) §1 para o comando `rsync`.

> ⚠️ **O HerdMaster original nunca deve ser alterado.** Use uma cópia local
> isolada no caminho irmão `../HerdMaster`.

---

### Passo 3 — deploy/.env

`ops/common.sh::load_aop_env` faz `source deploy/.env` e aborta
(`: "${VAR:?...}"`) se `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB` ou `REDIS_PASSWORD` estiverem ausentes. Senhas com
`change-me` são inválidas em produção.

☐ **Verificar que o arquivo existe:**

```bash
test -f deploy/.env && echo "OK   deploy/.env existe" || echo "FALTA deploy/.env"
```

☐ **Verificar que não há valores placeholder:**

```bash
if grep -qi 'change-me' deploy/.env 2>/dev/null; then
  echo "FAIL  deploy/.env contém 'change-me' — troque todas as senhas"
else
  echo "OK   deploy/.env sem placeholders"
fi
```

☐ **Verificar variáveis obrigatórias:**

> ℹ️ *Nota: rodar `source deploy/.env` num shell com `set -u` ativado pode causar falha caso o `.env` possua variáveis em branco não vinculadas.*

```bash
set -a; source deploy/.env; set +a
for v in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB REDIS_PASSWORD; do
  [[ -n "${!v}" ]] && echo "OK   $v definida" || echo "FALTA $v"
done
```

✅ **Pass:** arquivo existe, sem `change-me`, todas as variáveis definidas.
❌ **Fail:** `cp deploy/.env.example deploy/.env` e troque as senhas
(ver [`12-INSTALACAO.md`](12-INSTALACAO.md) §2,
[`13-VARIAVEIS-AMBIENTE.md`](13-VARIAVEIS-AMBIENTE.md) §1).

---

### Passo 4 — venv do control-plane

`ops/common.sh::uvicorn_bin()` procura primeiro
`/tmp/aop-control-plane-venv/bin/uvicorn`. Sem essa venv, o control-plane
não sobe.

☐ **Verificar venv e dependências:**

```bash
if [[ -x /tmp/aop-control-plane-venv/bin/uvicorn ]]; then
  echo "OK   uvicorn na venv"
  PYTHONPATH="./control-plane:../HerdMaster/src" \
  /tmp/aop-control-plane-venv/bin/python -c \
    "import app.main; print('OK   app.main importável')" \
    2>/dev/null || echo "FAIL  deps faltando ou HerdMaster ausente"
else
  echo "FALTA venv /tmp/aop-control-plane-venv"
fi
```

✅ **Pass:** `uvicorn` presente e `app.main` importável (conectado ao HerdMaster local).
❌ **Fail:** criar a venv (ver [`12-INSTALACAO.md`](12-INSTALACAO.md) §3) e validar HerdMaster clonado:

```bash
python3 -m venv /tmp/aop-control-plane-venv
/tmp/aop-control-plane-venv/bin/pip install --upgrade pip
/tmp/aop-control-plane-venv/bin/pip install -e ./control-plane
```

---

### Passo 5 — npm ci do frontend

`ops/start.sh` sobe o frontend com `npm run dev`. As dependências devem
estar instaladas (`web/node_modules`).

☐ **Verificar node_modules:**

```bash
if [[ -d web/node_modules ]]; then
  echo "OK   web/node_modules existe"
else
  echo "FALTA web/node_modules — rodar npm ci"
fi
```

✅ **Pass:** `web/node_modules` existe.
❌ **Fail:** instalar dependências:

```bash
( cd web && npm ci )
```

> **Referência:** [`11-PRE-REQUISITOS.md`](11-PRE-REQUISITOS.md) §4,
> [`12-INSTALACAO.md`](12-INSTALACAO.md) §4.

---

### Passo 6 — Portas livres e política +5

> **POLÍTICA DE PORTAS +5 (INEGOCIÁVEL):**
>
> Se uma porta nativa estiver ocupada por uma execução anterior ou outro
> serviço, `ops/common.sh::resolve_port()` **soma +5** à porta e testa
> novamente, repetindo até achar uma porta livre. **NUNCA** mata processos
> "zumbis" ou serviços legítimos do host.
>
> Portas ocupadas devem ser **REPORTADAS ao TL**, nunca mortas
> automaticamente (ver secção
> [Serviços em execução / zumbis](#serviços-em-execução--zumbis)).

☐ **Verificar portas nativas:**

```bash
for entry in \
  "Postgres:5432"       \
  "Redis:6379"          \
  "HerdMaster:8080"     \
  "Control-plane:8090"  \
  "Frontend:13000"      \
  "Prometheus:9090"     \
  "Grafana:3000"        \
  "Alertmanager:9093"   \
  "Blackbox:9115"      \
  "Remediation:9099"
do
  IFS=':' read -r name port <<< "$entry"
  if ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}"; then
    echo "OCUPADA  ${name} :${port}  → +5 aplicará deslocamento"
  else
    echo "LIVRE    ${name} :${port}"
  fi
done
```

✅ **Pass:** todas as portas nativas mostram `LIVRE`.
⚠️ **Atenção:** se alguma porta mostrar `OCUPADA`, `start.sh` aplicará +5
automaticamente. **Reporte ao TL** qual porta está ocupada e por quê.
**Não mate o processo.**

**Portas resolvidas atuais** (referência — podem mudar se o estado do host mudar):

| Serviço                  | Porta nativa | Porta resolvida |
|--------------------------|-------------|-----------------|
| Postgres                 | 5432        | 5437            |
| Redis                    | 6379        | 6384             |
| HerdMaster               | 8080        | 8085             |
| Control-plane (AOP API)  | 8090        | **8090**        |
| Frontend                 | 13000       | **13000**        |

> **Nota:** o control-plane (:8090) e o frontend (:13000) usam as portas
> nativas — estavam livres no ambiente atual. Se forem ocupadas, o +5
> deslocará e os healthchecks do Passo 9 devem usar a porta resolvida
> (visível na tabela final do `start.sh` ou em `ops/status360.py`).

---

### Passo 7 — Geração do token HerdMaster

`ops/common.sh::ensure_herdmaster_token()` gera (idempotentemente) o
token Bearer do acoplamento AOP ↔ HerdMaster em
`/tmp/aop-ops-runtime/herdmaster.token` (permissão `600`).
`write_prometheus_token()` mantém uma cópia `644` (sem newline final) em
`/tmp/aop-ops-runtime/prometheus.token` para o Prometheus, que roda como
`nobody` dentro do container e não consegue ler o arquivo `600`.

`start.sh` chama essas funções automaticamente, mas o pre-flight pode
pré-gerar para validar o mecanismo:

☐ **Pré-gerar token (idempotente):**

```bash
source ops/common.sh
ensure_herdmaster_token
write_prometheus_token
echo "herdmaster.token: $(stat -c '%a %n' /tmp/aop-ops-runtime/herdmaster.token)"
echo "prometheus.token: $(stat -c '%a %n' /tmp/aop-ops-runtime/prometheus.token)"
```

✅ **Pass:** `herdmaster.token` com permissão `600` e
`prometheus.token` com `644`.
❌ **Fail:** verificar que `openssl` está instalado (Passo 1) e que
`/tmp` é gravável.

> **Para rotacionar o token:** apague `/tmp/aop-ops-runtime/herdmaster.token`
> e rode `stop.sh` + `start.sh`
> (ver [`14-SEGREDOS-E-TOKENS.md`](14-SEGREDOS-E-TOKENS.md) §1).

> **Referência:** [`14-SEGREDOS-E-TOKENS.md`](14-SEGREDOS-E-TOKENS.md) §1–2.

---

## Subida

### Passo 8 — Subir o stack completo

Após os Passos 1–7 passarem, executar:

```bash
bash ops/start.sh
```

`start.sh` executa nesta ordem:

1. `require_cmd` de todos os binários + `load_aop_env`.
2. `resolve_runtime_ports` + `resolve_observability_ports` (política +5).
3. `docker_compose_aop up -d` (Postgres + Redis) → espera `pg_isready` / `redis-cli ping`.
4. `write_prometheus_token` + `render_observability_configs` → sobe observabilidade → espera healthchecks de Prometheus/Grafana/Alertmanager/Blackbox/Remediation.
5. `write_herdmaster_config` → sobe HerdMaster (idempotente) → espera `/metrics` com Bearer.
6. Sobe control-plane (`uvicorn app.main:app :8090`) → espera `/health` + `/health/ready`.
7. Sobe frontend (`npm run dev :13000`) → espera HTTP 200.
8. Imprime `print_status_table` (tabela com status de todos os componentes).

✅ **Pass:** `start.sh` termina sem erro e a tabela final mostra todos os
componentes como `up` / HTTP `200`.

> A tabela final do `start.sh` (`print_status_table`) já verifica
> Prometheus, Grafana, Alertmanager, Blackbox, Remediation Webhook,
> HerdMaster, Control-plane e Frontend. Confirme que todas as linhas
> mostram `200` ou `up`.

---

## Pós-subida (healthchecks)

### Passo 9 — Healthchecks HTTP

☐ **Control-plane — `/health` (inclui coupling com HerdMaster):**

> ⚠️ Se o +5 deslocou o control-plane (Passo 6), troque `8090` pela porta resolvida.

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool
```

✅ **Pass:** JSON com `"status": "ok"` e
`"coupling": {"status": "connected"}`.
⚠️ Se `coupling.status` for `"degraded"`, o token HerdMaster não foi
injetado corretamente — verificar `HERDMASTER_TOKEN` no processo uvicorn
(ver [`13-VARIAVEIS-AMBIENTE.md`](13-VARIAVEIS-AMBIENTE.md) §3).

☐ **Control-plane — `/health/ready` (Postgres + Redis):**

> ⚠️ Verifique a porta resolvida do control-plane se `8090` foi deslocada.

```bash
curl -s http://127.0.0.1:8090/health/ready | python3 -m json.tool
```

✅ **Pass:** JSON com `"status": "ok"` (Postgres e Redis acessíveis).
❌ **Fail:** verificar que os containers subiram:

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps
```

☐ **Frontend (Next.js):**

> ⚠️ Verifique a porta resolvida do frontend se `13000` foi deslocada.

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:13000
```

✅ **Pass:** `200`.
❌ **Fail:** checar `ops/logs/aop-frontend.log`.

☐ **HerdMaster `/metrics` (com Bearer token):**

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $(tr -d '\r\n' < /tmp/aop-ops-runtime/herdmaster.token)" \
  http://127.0.0.1:8080/metrics
```

> ⚠️ Se o +5 deslocou o HerdMaster (Passo 6), troque `8080` pela porta
> resolvida (ex.: `8085`). A porta resolvida aparece na tabela final do
> `start.sh` e no `print_status_table`.

✅ **Pass:** `200`.
❌ **Fail:** checar `ops/logs/herdmaster.log` e o config TOML em
`/tmp/aop-ops-runtime/herdmaster.config.toml`.

---

### Passo 10 — status360.py (dashboard de squads)

```bash
python3 ops/status360.py
```

✅ **Pass:** tabela renderizada com semáforo (🟢/🟡/🔴/⚪) e ETA por task,
lendo o ledger `CHECKIN_OUT.md`.

> Para monitoramento contínuo: `python3 ops/status360.py --watch`
> (refresh 60s).

---

## Serviços em execução / zumbis

### Princípio fundamental

**Portas já ocupadas por execuções anteriores (ou por serviços legítimos do
host) devem ser REPORTADAS ao TL — NUNCA mortas automaticamente.**

### Política +5 (implementada em `ops/common.sh::resolve_port`)

```bash
resolve_port() {
  # ...
  while port_listening "${candidate}"; do
    candidate=$((candidate + 5))    # soma +5 e testa de novo
  done
  # NUNCA chama kill neste fluxo
}
```

Ao encontrar uma porta ocupada, **soma +5** e testa novamente, repetindo
até achar uma porta livre. Em nenhum momento `start.sh` ou o fluxo de
pre-flight mata processos em portas ocupadas — o deslocamento +5 é a
**única** estratégia de resolução.

### Por que nunca matar

- O processo na porta pode ser uma **execução anterior legítima** de outro
  agente da squad (ex.: um HerdMaster em uso por outro fluxo).
- Matar um processo alheio pode corromper estado (DB, sockets, PID files).
- A política +5 garante que o stack sobe mesmo com portas ocupadas, sem
  efeitos colaterais.

### Como identificar processos em portas

```bash
# Listar PID e comando dono de cada porta ocupada:
for port in 5432 6379 8080 8090 13000; do
  pid="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -1)"
  if [[ -n "$pid" ]]; then
    proc="$(ps -p "$pid" -o comm= 2>/dev/null || echo '?')"
    echo ":${port}  pid=${pid}  (${proc})"
  fi
done
```

### Como identificar PID files gerenciados

`start.sh` grava PID files em `/tmp/aop-ops-run/`:

| Arquivo                              | Serviço                |
|--------------------------------------|------------------------|
| `/tmp/aop-ops-run/aop-frontend.pid`   | Frontend (Next.js)     |
| `/tmp/aop-ops-run/aop-control-plane.pid` | Control-plane (uvicorn) |
| `/tmp/aop-ops-run/herdmaster.pid`     | HerdMaster             |

```bash
# Verificar PID files e se os processos ainda vivem:
for f in /tmp/aop-ops-run/*.pid; do
  [[ -f "$f" ]] || continue
  pid="$(tr -dc '0-9' < "$f")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "VIVO    $f  pid=$pid"
  else
    echo "MORTO   $f  pid=$pid  (PID file stale — start.sh ignora)"
  fi
done
```

> PID files "stale" (processo morto, arquivo presente) **não** causam
> bloqueio — `start.sh` detecta via `pid_alive()` e prossegue com a subida.

### Como parar serviços corretamente

Para encerrar uma execução anterior de forma limpa, use:

```bash
bash ops/stop.sh
```

`stop.sh` para os serviços na ordem inversa da subida:
1. `stop_pid_file` (SIGTERM → espera 20s → SIGKILL se preciso) para cada PID file.
2. `kill_port_processes` para limpar listeners não gerenciados em cada porta.
3. `docker_compose_obs down` (observabilidade).
4. `docker_compose_aop stop postgres redis` (preserva volumes — **não** usa `down`).

> ⚠️ **Não use** `kill -9` manual em portas ocupadas. Se precisar parar
> algo, use `stop.sh`. Se a porta persistir ocupada após `stop.sh`,
> **reporte ao TL** com a evidência (`lsof`/`ss` output) e aguarde
> orientação. **Nunca** mate o HerdMaster original.

### Fluxo de decisão

```
Porta ocupada detectada no pre-flight?
  │
  ├── Sim → 1. Reportar ao TL (porta, PID, processo)
  │         2. NÃO matar — start.sh aplicará +5 automaticamente
  │         3. Anotar a porta resolvida na tabela do Passo 6
  │
  └── Não → Prosseguir normalmente para o Passo 7
```

---

## Referências rápidas

| Artefato               | Caminho                              |
|------------------------|--------------------------------------|
| Pré-requisitos         | [`11-PRE-REQUISITOS.md`](11-PRE-REQUISITOS.md) |
| Instalação             | [`12-INSTALACAO.md`](12-INSTALACAO.md) |
| Variáveis de ambiente  | [`13-VARIAVEIS-AMBIENTE.md`](13-VARIAVEIS-AMBIENTE.md) |
| Segredos e tokens      | [`14-SEGREDOS-E-TOKENS.md`](14-SEGREDOS-E-TOKENS.md) |
| Compose e serviços     | [`15-COMPOSE-E-SERVICOS.md`](15-COMPOSE-E-SERVICOS.md) |
| `common.sh`            | `ops/common.sh`                      |
| `start.sh`             | `ops/start.sh`                       |
| `stop.sh`              | `ops/stop.sh`                        |
| `status360.py`         | `ops/status360.py`                   |
| `.env`                 | `deploy/.env` (não versionado)       |
| Compose base           | `deploy/docker-compose.yml`          |
| Compose observabilidade | `../HerdMaster/deploy/observability/docker-compose.yml` |
| venv                   | `/tmp/aop-control-plane-venv`        |
| Runtime (token, config) | `/tmp/aop-ops-runtime`              |
| PID files              | `/tmp/aop-ops-run`                   |
| Logs                   | `ops/logs/`                          |

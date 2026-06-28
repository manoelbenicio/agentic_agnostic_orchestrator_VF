# 11 — Pré-requisitos

## 1. Layout de diretórios (obrigatório)

A AOP **exige** o HerdMaster como projeto **irmão** no mesmo diretório-pai. Em `ops/common.sh`:

```bash
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AOP_DIR="$(cd "${OPS_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${AOP_DIR}/.." && pwd)"
HERDMASTER_DIR="${ROOT_DIR}/HerdMaster"
OBS_DIR="${HERDMASTER_DIR}/deploy/observability"
```

Layout esperado:

```
<ROOT>/
├── AOP/                 # este repositório
│   ├── control-plane/
│   ├── web/
│   ├── deploy/
│   └── ops/
└── HerdMaster/          # projeto irmão (operacional)
    ├── src/
    └── deploy/observability/   # compose de observabilidade
```

> Se o HerdMaster não estiver em `../HerdMaster`, `start.sh` falha ao subir a observabilidade e ao iniciar o HerdMaster. **Confirme o layout antes de qualquer coisa.**

> **Importante (origem somente-leitura):** o HerdMaster operacional vive em outro projeto (ex.: `.../Multi_Orchestration_Project_Tasks/HerdMaster`). Esse original **nunca** deve ser alterado. Use uma **cópia local isolada** no caminho irmão `../HerdMaster` — copiar, não symlink (symlink escreveria de volta no original ao rodar). Exemplo de cópia enxuta (exclui artefatos voláteis):
> ```bash
> rsync -a \
>   --exclude '.git' --exclude 'build' --exclude 'scratch' --exclude '__pycache__' \
>   --exclude '*.pyc' --exclude 'herdmaster.db' --exclude '*.log' \
>   "/caminho/origem/HerdMaster/" "$(pwd)/../HerdMaster/"
> ```

### Verificação

```bash
test -d "$(pwd)/../HerdMaster" && echo "HerdMaster OK" || echo "FALTA HerdMaster irmão"
test -f "$(pwd)/../HerdMaster/deploy/observability/docker-compose.yml" \
  && echo "observability compose OK" || echo "FALTA observability compose"
```

---

## 2. Binários obrigatórios

`ops/start.sh` chama `require_cmd` para cada um destes (falha imediata se faltar):

```bash
require_cmd docker
require_cmd curl
require_cmd lsof
require_cmd ss
require_cmd npm
require_cmd setsid
```

`ops/flush-restart.sh` também exige `find`. `ops/db-backup.sh`/`db-restore.sh` exigem `docker` (usam `docker exec` no container Postgres).

| Binário   | Usado para | Origem |
|-----------|-----------|--------|
| `docker`  | compose base + observabilidade, `docker exec` | `start/stop/flush/db-*` |
| `curl`    | healthchecks HTTP | `common.sh` (`http_code`, `wait_http_200`) |
| `lsof`    | descobrir PID por porta | `common.sh` (`record_listener_pid`, `kill_port_processes`) |
| `ss`      | checar portas em escuta | `common.sh` (`port_listening`) |
| `npm`     | rodar o frontend (`npm run dev`) | `start.sh` |
| `setsid`  | desacoplar processos de longa duração (process group) | `start.sh` |
| `find`    | limpeza de caches no flush | `flush-restart.sh` |
| `openssl` | gerar token HerdMaster (fallback: `sha256sum`) | `common.sh` (`ensure_herdmaster_token`) |

### Verificação

```bash
for c in docker curl lsof ss npm setsid find openssl; do
  command -v "$c" >/dev/null 2>&1 && echo "OK  $c" || echo "FALTA $c"
done
```

---

## 3. Runtime Python do control-plane

`ops/common.sh` resolve o `uvicorn` assim:

```bash
uvicorn_bin() {
  if [[ -x "/tmp/aop-control-plane-venv/bin/uvicorn" ]]; then
    printf '%s\n' "/tmp/aop-control-plane-venv/bin/uvicorn"
  elif command -v uvicorn >/dev/null 2>&1; then
    command -v uvicorn
  else
    die "uvicorn not found; install AOP control-plane dependencies first"
  fi
}
```

Ou seja, o caminho **preferencial** é uma venv em `/tmp/aop-control-plane-venv`. A instalação dessa venv está documentada em [`12-INSTALACAO.md`](12-INSTALACAO.md).

O control-plane sobe com:

```
uvicorn app.main:app --host 127.0.0.1 --port 8090
PYTHONPATH=${AOP_DIR}/control-plane:${HERDMASTER_DIR}/src
```

> Repare no `PYTHONPATH`: o control-plane importa pacotes do **HerdMaster** (`herdmaster.*`). Sem `HerdMaster/src` no path, imports como `from herdmaster.acl.engine import AclEngine` (usado no E2E) falham.

---

## 4. Frontend (Node)

`web/package.json` fixa as versões (sem ranges abertos relevantes):

- `next` **16.2.9**, `react`/`react-dom` **19.2.7**, `@xyflow/react` **12.11.1** (canvas do squad-builder), `tailwindcss` **4.3.1**, `typescript` **6.0.3**.

Scripts: `dev` (`next dev`), `build` (`next build`), `start` (`next start`), `lint` (`eslint`).

> A versão do Node não está fixada em `package.json` (sem campo `engines`). Recomendação para a squad: usar Node LTS compatível com Next 16 (verificar na doc oficial do Next no momento do deploy). **Não verificado em runtime aqui.**

### Verificação

```bash
node --version && npm --version
( cd web && npm ci )   # instala dependências travadas no package-lock
```

---

## 5. Recursos de sistema (orientativo) e Política de Portas

- Docker com permissão para o usuário atual (`docker ps` sem `sudo`).
- `/tmp` gravável (runtime e venv vivem lá — ver [`14-SEGREDOS-E-TOKENS.md`](14-SEGREDOS-E-TOKENS.md)).

### Política de Portas +5

Se uma porta nativa estiver ocupada, **somar +5 até achar uma porta livre**. **NUNCA** mate processos "zumbis" de outras execuções ou de serviços legítimos do host.

> **Importante (Natureza Dinâmica):** A porta resolvida é **DINÂMICA** e depende do que estiver ocupado no momento do `start`. A tabela abaixo é apenas um **EXEMPLO** do estado atual de ocupação, não são valores fixos. 
> 
> **Ressalva:** Como as portas nativas muitas vezes ficam ocupadas por uma execução ANTERIOR da própria AOP, aplicar +5 nesse cenário subiria instâncias DUPLICADAS. O caminho mais limpo é rodar `ops/stop.sh` antes, para liberar as portas nativas, evitando o acúmulo de serviços.

| Serviço | Porta Nativa | Porta Resolvida (Exemplo Atual) |
|---------|--------------|---------------------------------|
| Postgres | 5432 | **5437** |
| Redis | 6379 | **6384** |
| HerdMaster | 8080 | **8085** |
| Control-plane (AOP API) | 8090 | **8090** (livre) |
| Frontend | 13000 | **13000** (livre) |
| Prometheus | 9090 | **9090** (livre) |
| Grafana | 3000 | **3005** |
| Alertmanager | 9093 | **9098** |
| Blackbox Exporter | 9115 | **9120** |
| Remediation Engine | 9099 | **9104** |

### Verificação de portas

O script de inicialização implementa a política de `+5` automaticamente. Certifique-se de que o layout de portas acima foi compreendido.

# 12 — Instalação

> Pré-condição: [`11-PRE-REQUISITOS.md`](11-PRE-REQUISITOS.md) atendido (layout irmão AOP+HerdMaster, binários, portas livres).

Esta página descreve a **preparação** do ambiente até o ponto em que `ops/start.sh` consegue subir o stack. **Não executa o deploy** — os comandos abaixo são o roteiro que a squad seguirá.

---

## 1. Clonar/posicionar os repositórios irmãos

```bash
# Estrutura final desejada:
#   <ROOT>/AOP        (este repo)
#   <ROOT>/HerdMaster (projeto irmão, operacional)
ls -d ../AOP ../HerdMaster
```

---

## 2. Criar o arquivo de ambiente

O `.env` real **não** é versionado; existe apenas o template `deploy/.env.example`.

```bash
cp deploy/.env.example deploy/.env
# Editar deploy/.env e trocar TODAS as senhas (ver 13-VARIAVEIS-AMBIENTE.md)
```

Conteúdo do template (`deploy/.env.example`):

```
POSTGRES_USER=aop_dev
POSTGRES_PASSWORD=change-me-postgres-password
POSTGRES_DB=aop
REDIS_PASSWORD=change-me-redis-password
```

> `common.sh` valida que `POSTGRES_USER`, `POSTGRES_PASSWORD` e `POSTGRES_DB` existem (`: "${VAR:?...}"`). Se faltar, o boot aborta.

---

## 3. Preparar a venv do control-plane

O caminho preferencial é `/tmp/aop-control-plane-venv` (ver `uvicorn_bin()` em `common.sh`). O control-plane é um pacote Python com `control-plane/pyproject.toml`.

```bash
python3 -m venv /tmp/aop-control-plane-venv
/tmp/aop-control-plane-venv/bin/pip install --upgrade pip
# instala o pacote do control-plane (uvicorn, fastapi, psycopg, redis, etc. via pyproject)
/tmp/aop-control-plane-venv/bin/pip install -e ./control-plane
# para desenvolvimento/testes, instale tambem as dependencias opcionais:
/tmp/aop-control-plane-venv/bin/pip install -e "./control-plane[dev]"
```

### Verificação

```bash
/tmp/aop-control-plane-venv/bin/uvicorn --version
/tmp/aop-control-plane-venv/bin/python -c "import fastapi, psycopg, redis; print('deps OK')"
```

> O conjunto exato de dependências é definido por `control-plane/pyproject.toml`. A squad deve confirmar que `psycopg` (driver Postgres) e `redis` estão resolvidos — são usados em `app/main.py` (`/health/ready`).

---

## 4. Instalar dependências do frontend

```bash
cd web
npm ci          # usa package-lock; instala Next 16, React 19, @xyflow/react, tailwind 4
cd ..
```

---

## 5. Confirmar que o HerdMaster sobe standalone

O `start.sh` invoca `herdmaster start --http --config <gerado>`. Garanta que o CLI `herdmaster` está disponível no ambiente (instalado a partir de `../HerdMaster/src`).

### Verificação

```bash
PYTHONPATH=../HerdMaster/src command -v herdmaster || echo "instalar herdmaster CLI"
```

> A instalação do HerdMaster em si é responsabilidade do projeto irmão; consulte a documentação do HerdMaster. A AOP apenas o invoca.

---

## 6. Primeira subida (quando a squad for executar)

```bash
bash AOP/ops/start.sh
```

Sequência executada por `start.sh` (resumo — detalhes em [`20-OPERACAO/21-SUBIR-E-DERRUBAR.md`](../20-OPERACAO/21-SUBIR-E-DERRUBAR.md)):

1. `require_cmd` de todos os binários + `load_aop_env`.
2. `docker compose ... up -d` (postgres + redis) e espera `pg_isready` / `redis-cli ping`.
3. Sobe observabilidade (`../HerdMaster/deploy/observability`) e espera Prometheus/Grafana/Alertmanager/Blackbox/Remediação.
4. Gera token + `herdmaster.config.toml`, sobe HerdMaster em `:8080` (idempotente).
5. Sobe control-plane (`uvicorn app.main:app :8090`) e espera `/health` + `/health/ready`.
6. Sobe frontend (`npm run dev :13000`).
7. Imprime `print_status_table`.

### Verificação pós-subida

```bash
curl -s http://127.0.0.1:8090/health
curl -s http://127.0.0.1:8090/health/ready
curl -s http://127.0.0.1:13000 -o /dev/null -w '%{http_code}\n'
```

> Detalhes de `/health` retornando também `coupling` em [`30-COMPONENTES/31-CONTROL-PLANE.md`](../30-COMPONENTES/31-CONTROL-PLANE.md).

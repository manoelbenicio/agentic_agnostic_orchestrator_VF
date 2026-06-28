# Imagens de Producao

## Escopo

A Fase 6 adiciona imagens versionaveis para producao sem alterar o fluxo local do `ops/start.sh`.
Por padrao, `deploy/docker-compose.yml` continua subindo apenas Postgres, Redis e registry. Os
servicos `control-plane` e `web` ficam no profile `prod`.

## Build local

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml --profile prod build control-plane web
```

## Subir runtime containerizado

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml --profile prod up -d
```

## Otimizacoes aplicadas

- `control-plane/Dockerfile`: base `python:3.12-slim`, install sem cache, bytecode compilado e usuario sem login.
- `web/Dockerfile`: build multi-stage Node 22 Alpine e runtime com `.next/standalone`.
- `.dockerignore` por componente para excluir `node_modules`, `.next`, venvs, caches, testes e artefatos locais.
- `control-plane/pyproject.toml`: `pytest` saiu das dependencias runtime e ficou em `.[dev]`.

## Publicacao no registry local

```bash
docker tag aop/control-plane:local 127.0.0.1:5000/aop/control-plane:local
docker tag aop/web:local 127.0.0.1:5000/aop/web:local
docker push 127.0.0.1:5000/aop/control-plane:local
docker push 127.0.0.1:5000/aop/web:local
```

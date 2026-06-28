# 15 — Compose e Serviços base

Origem da verdade: `deploy/docker-compose.yml` (íntegra abaixo) + `deploy/.env`.

## 1. Conteúdo do compose (verbatim do repositório)

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - aop_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d \"$${POSTGRES_DB}\""]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 10s
    networks:
      - aop_net

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a \"$${REDIS_PASSWORD}\" ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 5s
    networks:
      - aop_net

networks:
  aop_net:
    driver: bridge

volumes:
  aop_postgres_data:
```

---

## 2. Serviços

### Postgres
- **Imagem:** `pgvector/pgvector:pg17` (Postgres 17 com extensão `pgvector` — habilita embeddings/busca vetorial, relevante para futuras features de RAG/memória).
- **Porta:** `127.0.0.1:5432:5432` (loopback — não exposto à rede).
- **Volume:** `aop_postgres_data` (persistência; preservado por `stop.sh`, destruído só no caminho `CONFIRMO` do `flush-restart.sh`).
- **Healthcheck:** `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`.
- **`restart: unless-stopped`** — sobe sozinho após reboot do host (a menos que parado explicitamente).

### Redis
- **Imagem:** `redis:7-alpine`.
- **Porta:** `127.0.0.1:6379:6379` (loopback).
- **Healthcheck:** `redis-cli -a "$REDIS_PASSWORD" ping | grep PONG`.
- **Sem volume** → dados Redis são efêmeros (cache/fila; perda aceitável no design atual).
- **Segurança:** Utiliza `requirepass` via parâmetro `--requirepass` no command para proteger acesso.

### Rede e volume
- **Rede:** `aop_net` (bridge dedicada).
- **Volume nomeado:** `aop_postgres_data`.

---

## 3. Como o compose é invocado

`common.sh` sempre passa o `--env-file` e o arquivo de compose explícitos:

```bash
docker_compose_aop() {
  docker compose --env-file "${AOP_ENV_FILE}" -f "${AOP_COMPOSE}" "$@"
}
```

Onde `AOP_ENV_FILE=deploy/.env` e `AOP_COMPOSE=deploy/docker-compose.yml`.

> **Nome do container:** os scripts de backup assumem `deploy-postgres-1` (padrão do Compose v2: `<dir>-<service>-<index>`, sendo o dir `deploy`). Confirme com `docker ps`.

---

## 4. Ciclo de vida dos containers base

| Ação | Comando efetivo | Efeito no volume |
|------|------------------|------------------|
| Subir | `docker compose ... up -d` (`start.sh`) | cria/preserva |
| Parar | `docker compose ... stop postgres redis` (`stop.sh`) | **preserva** |
| Reset destrutivo | `docker compose ... down` após DROP de schemas (`flush-restart.sh`, só com `CONFIRMO`) | preserva o volume nomeado, mas os dados foram apagados via SQL |

> `stop.sh` usa `stop` (não `down`) de propósito, para **não** remover a rede/volume. O `flush-restart.sh` é o único caminho destrutivo, e ainda assim protegido por confirmação interativa `CONFIRMO`.

### Verificação

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T postgres \
  pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T redis redis-cli ping
docker volume ls | grep aop_postgres_data
```

---

## 5. O que o compose **não** inclui (importante)

O compose base sobe **apenas** Postgres e Redis. **Não** sobem via compose:

- **HerdMaster** (`:8080`) → processo nativo iniciado por `start.sh` (`herdmaster start --http`).
- **Control-plane** (`:8090`) → uvicorn iniciado por `start.sh`.
- **Frontend** (`:13000`) → `npm run dev` iniciado por `start.sh`.
- **Observabilidade** (Prometheus/Grafana/etc.) → compose **separado** em `../HerdMaster/deploy/observability`.

Esse desenho é intencional: o `docker-compose.yml` da AOP é mínimo (só estado persistente), e os processos de aplicação rodam como processos de host gerenciados por PID files em `/tmp/aop-ops-run` (ver [`20-OPERACAO/21-SUBIR-E-DERRUBAR.md`](../20-OPERACAO/21-SUBIR-E-DERRUBAR.md)).

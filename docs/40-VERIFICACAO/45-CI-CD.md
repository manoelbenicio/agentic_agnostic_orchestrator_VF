# 45 — CI/CD

O pipeline principal vive em `.github/workflows/ci.yml` e roda em `push`, `pull_request` e `workflow_dispatch`.

## Jobs

- `Backend Python`: instala `control-plane`, sobe Postgres/Redis efêmeros, compila módulos Python e executa a suíte unitária focada.
- `Frontend Next.js`: executa `npm ci`, `npm run lint` e `npm run build`.
- `Configs and Contracts`: valida JSON/YAML, shell scripts e `docker compose config`.

## Premissas

- O CI não usa segredos persistentes.
- O arquivo `deploy/.env` é gerado somente no runner com credenciais efêmeras de teste.
- Testes E2E reais, k6 e deploy completo continuam sendo executados por fluxos operacionais dedicados, não como gate obrigatório de PR.

# AOP F7 E2E Final Plan

## Objetivo

F7 valida a camada final antes do aceite operacional: contratos de API, rotas UI, fluxos críticos, observabilidade, performance leve e acessibilidade. Este plano evita execução exaustiva por padrão; qualquer rodada pesada precisa de opt-in explícito.

## Escopo

- Diretório de trabalho: `AOP/e2e/**`.
- API base: `AOP_E2E_BASE_URL`, default `http://127.0.0.1:8090`.
- Web base: `AOP_E2E_WEB_URL`, default `http://127.0.0.1:13000`.
- Evidências: JSON/Markdown gerados em `AOP/e2e/`.

## Gates F7

| Gate | Cobertura | Critério de aceite |
| --- | --- | --- |
| G1 Readiness | `/health`, `/health/ready`, `/metrics` | API responde, readiness não degradado, métrica `aop_control_plane_up 1` presente |
| G2 API Contracts | Projetos, seats, sessions, tasks, topology, FinOps, tracing | Reusar `test_contracts_wave1.py`; falha em contrato válido bloqueia F7 |
| G3 UI Routes | Shell e rotas principais Next | HTTP 200, HTML válido, sem marcadores de runtime error |
| G4 Critical Journey | Criar projeto, registrar seats, acionar sessão/tarefa, gerar tracing/FinOps | Evidência correlacionada por `run_id`; skips só para dependência externa indisponível |
| G5 Observability | `/metrics`, tracing por agente/runtime, rollup FinOps | Eventos consultáveis e custo agregado consistente |
| G6 Perf Smoke | Latência p95 aproximada em endpoints leves | Apenas amostra curta por padrão; budget inicial: p95 <= 1500 ms |
| G7 A11y Smoke | Rotas UI principais | Placeholder até Playwright/axe entrar; não bloqueia enquanto scaffold |
| G8 Evidence | Relatórios e artefatos | `F7_EVIDENCE.json` e `REPORT_F7.md` gerados por rodada |

## Execução

Listar plano sem rede:

```bash
cd AOP/e2e
python f7_harness.py --profile plan
```

Smoke leve:

```bash
cd AOP/e2e
python f7_harness.py --profile smoke
```

Rodada full não exaustiva:

```bash
cd AOP/e2e
python f7_harness.py --profile full
```

Rodada exaustiva exige opt-in duplo:

```bash
cd AOP/e2e
python f7_harness.py --profile exhaustive --allow-exhaustive
```

## Política de Resultado

- `passed`: todos os checks aplicáveis passaram.
- `skipped`: dependência externa ausente ou capability ainda não instalada, com motivo explícito.
- `failed`: contrato inesperado, erro HTTP não tolerado, regressão de HTML, ou budget de perf estourado.
- `blocked`: harness impedido de executar por configuração inválida.

## Backlog Controlado

- Integrar Playwright + axe para G7 quando a stack de browser test estiver instalada.
- Adicionar captura de screenshot por rota UI quando houver runner de browser.
- Promover G4 para fluxo browser real após estabilizar autenticação/sessões.
- Definir budgets finais de performance com base em baseline medido em ambiente CI/local.

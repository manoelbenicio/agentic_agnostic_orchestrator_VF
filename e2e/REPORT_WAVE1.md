# AOP Wave 1 E2E Contract Report

## Retomada

- Dono atual: `CODEX_55#0`
- Handoff: `NVIDIA_NEMOTRON -> CODEX_55#0`
- Auditoria inicial: `AOP/e2e/` continha `smoke_e2e.py`, `REPORT.md` e `evidence.json`; não havia pytest de contratos nem `REPORT_WAVE1.md`.

## Cobertura

- API contract tests: `/health`, `/health/ready`, `/metrics`, `/projects`, `/seats`, `/sessions`, `/tasks`, `/squads/{id}/topology`, `/finops/*`, `/tracing/*`.
- UI smoke: GET das rotas Next em `:13000` para `/`, `/projects`, `/issues`, `/seats`, `/sessions`, `/finops`, `/observability`, `/live`, `/settings`, `/inbox`, `/my-issues`, `/squad-builder`.
- Política de tolerância: skip explícito apenas quando API, Next ou runtime externo não responde; respostas HTTP válidas são verificadas por contrato.

## Arquivos

- `smoke_e2e.py`: mantido como smoke legado pós-crash.
- `test_contracts_wave1.py`: contratos pytest/httpx e UI smoke.
- `REPORT_WAVE1.md`: relatório consolidado desta retomada.

## Execução

Comandos recomendados:

```bash
cd AOP/e2e
pytest -q
```

Variáveis opcionais:

```bash
AOP_E2E_BASE_URL=http://127.0.0.1:8090
AOP_E2E_WEB_URL=http://127.0.0.1:13000
```

Resultado validado nesta retomada:

```text
../control-plane/.venv/bin/python -m pytest -q
19 passed in 25.07s
```

Evidência visual:

- `AOP/.planning/evidence/QA-E2E-resume.png`

## Critério

- Verde: contratos respondem e batem com o formato esperado.
- Skip: dependência externa ausente, com motivo explícito no output pytest.
- Falha: endpoint respondeu com contrato inesperado, erro de framework na UI ou payload incompatível.

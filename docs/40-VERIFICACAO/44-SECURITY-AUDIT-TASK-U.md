# Auditoria de Seguranca - Task U

Data: 2026-06-27

## Escopo

- Endpoints do control-plane FastAPI.
- Repositorios SQL usados por issues, projects, inbox, registry, seats, sessions e finops.
- Superficie de execucao externa em sessions/executors.

## Achados

- Queries de repositorio usam parametros `%s` para valores vindos de API. As clausulas `WHERE` dinamicas observadas sao montadas a partir de listas internas fixas e os valores seguem parametrizados.
- `FinOpsRepository.rollup_by_dimension()` interpola uma expressao SQL, mas a expressao vem somente do mapa interno `_DIMENSIONS`. Entrada desconhecida ou maliciosa gera `ValueError`.
- Comandos de provedores em `sessions_api/service.py` sao tokenizados com `shlex.split()` e executados via `subprocess.run(args, ...)`, sem `shell=True`.
- A configuracao CORS usa `allow_credentials=True`; foi adicionada validacao para rejeitar `AOP_CORS_ORIGINS=*`, evitando combinacao insegura em deploy.

## Evidencia de hardening

- `app/settings.py` rejeita wildcard CORS quando credenciais estao habilitadas.
- `app/tests/test_security_config.py` cobre rejeicao de wildcard e aceite de origens explicitas.
- `finops/tests/test_security_validation.py` cobre rejeicao de payload SQL no nome da dimensao antes de qualquer acesso ao banco.
- `finops/tests/test_regularization.py` cobre tentativa de injecao SQL no nome da dimensao e confirma que a tabela segue utilizavel.

## Validacao executada

- `python -m py_compile app/settings.py app/tests/test_security_config.py finops/repository.py finops/tests/conftest.py finops/tests/test_regularization.py finops/tests/test_security_validation.py`: OK.
- `pytest app/tests/test_security_config.py -q`: 2 passed.
- `pytest finops/tests/test_security_validation.py -q`: 1 passed.
- `pytest finops/tests/test_regularization.py -q`: bloqueado no ambiente local porque `127.0.0.1:5437` recusou conexao; o teste permanece valido para execucao com Postgres ativo.

## Risco residual

- A API segue assumindo fronteira local/deploy confiavel para autenticacao. Se exposta fora de localhost/rede controlada, a recomendacao e adicionar autenticacao por token e autorizacao por rota antes da exposicao.

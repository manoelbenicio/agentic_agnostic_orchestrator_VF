# Changelog

Todos os lançamentos notáveis do HerdMaster são documentados aqui.
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
o projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.0] — 2026-06-21

Primeira versão estável. Plano de controle de orquestração multi-agente em tempo real
sobre o Herdr.

### Adicionado (Added)

- **Camada de dados** (`db/`): SQLite WAL, 6 tabelas (`agents`, `projects`, `tasks`,
  `messages`, `health_events`, `project_history`) + 8 índices; claim atômico via CAS.
- **Configuração** (`config.py`): carga/validação TOML, recarga a quente, logging JSON (structlog).
- **Barramento de mensagens** (`bus/`): servidor socket Unix asyncio, JSON-RPC 2.0,
  pub/sub (unicast/broadcast/group), persistência, TTL, WebSocket, fallback em arquivo.
- **Adaptador Herdr** (`herdr/`): única fronteira de I/O; agent list/pane read/pane send/
  agent wait; subprocess com lista de args (sem injeção de shell).
- **Fila de tarefas** (`dispatch/queue.py`): máquina de estados, prioridades, dependências,
  reatribuição automática.
- **Injetor de despacho** (`dispatch/injector.py`): injeção idle-gated, chunking de prompts
  longos, fallback em arquivo, retry com backoff.
- **Watchdog** (`watchdog/`): detecção em 3 camadas, FSM de saúde, auto-recuperação, escalação.
- **ACL** (`acl/engine.py`): políticas por papel, default-deny, curingas, grupos, troca a quente.
- **Modo Projeto** (`project/`): planner + recomendação de squad + cálculo de ETA (faixa
  otimista/esperado/pessimista) + decomposição em tarefas.
- **API de controle** (`api/server.py`): socket Unix + HTTP localhost (token obrigatório);
  todos os endpoints do §10; envios mediados por ACL; streaming WebSocket.
- **Dashboard TUI** (`tui/dashboard.py`): 5 painéis em tempo real; fallback textual→rich→texto.
- **CLI** (`cli.py`): `start`, `stop`, `status`, `agents`, `tasks`, `projects`, `metrics`,
  `config reload`.
- **Testes**: 80 testes (unitários + E2E de ciclo de vida completo), Herdr mockado.
- **Documentação**: README, TECHNICAL_DESIGN, API_REFERENCE, TROUBLESHOOTING, PARALLEL_TASKS,
  notas de versão PT-BR, quickstart PT-BR, 3 diagramas HTML animados (macro/micro/deep).
- **Empacotamento/Deploy**: pyproject (PEP 621), unit systemd `--user`, script de instalação.

### Corrigido (Fixed)

- ACL: `worker→worker` indevidamente permitido (resolução de papéis do alvo). Corrigido.
- Fila: prioridade `critical` (0) tratada como falsy e ordenada como `normal`. Corrigido.
- API: `_restart_agent` usava atributo inexistente, causando 500 no restart. Corrigido.

### Segurança (Security)

- API de controle vinculada apenas a localhost; modo HTTP exige token bearer.
- Identidade de agente derivada do pane do Herdr (não falsificável).
- Toda comunicação do barramento mediada pela ACL (default-deny).
- `.gitignore` endurecido: exclui `.env`, chaves, credenciais, `config.toml`, db/log/sock.

### Limitações conhecidas (Known limitations)

- Bind de socket Unix bloqueado em sandbox WSL (`PermissionError`); roda normalmente em
  host Linux. Runtime validado em processo pelos testes E2E.

[1.0.0]: https://github.com/manoelbenicio/customized_herdr/releases/tag/v1.0.0

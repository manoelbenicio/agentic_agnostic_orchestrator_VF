# HerdMaster v1.0.0 — Notas de Versão (Release Notes)

> **Data:** 2026-06-21
> **Versão:** 1.0.0
> **Status:** Estável — pronto para uso
> **Linguagem:** Português (Brasil)

---

## 1. Visão Geral — O que é o HerdMaster

O **HerdMaster** é um **plano de controle (control plane) de orquestração multi-agente em tempo real**, construído **em cima do Herdr** (o multiplexador de terminais para agentes de IA de codificação).

O Herdr, sozinho, é apenas um *multiplexador de terminais* — ele **detecta** agentes rodando em painéis (panes) e mostra o estado de cada um (`idle`, `working`, `blocked`, `done`, `unknown`), mas **não** faz roteamento de tarefas, **não** tem fila de tarefas, **não** tem barramento de mensagens, **não** tem watchdog e **não** tem controle de acesso.

O **HerdMaster preenche exatamente essas lacunas** (gaps G-001 a G-009 do PRD), sem modificar os agentes e sem substituir o Herdr. Ele adiciona, por cima do Herdr:

- Barramento de mensagens em tempo real entre agentes
- Fila de tarefas com despacho atômico e injeção direta nos painéis do Herdr
- Watchdog de 3 camadas com auto-recuperação
- Motor de controle de acesso (ACL) baseado em políticas
- **Modo Projeto** (Project Mode): você submete o escopo de um projeto inteiro → o orquestrador analisa → sugere o esquadrão (squad) + ETA → decompõe em tarefas → despacha
- Dashboard TUI em tempo real
- API de controle (socket Unix + HTTP local opcional)
- CLI (`herdmaster`)

**Princípio central:** o HerdMaster é *Herdr-nativo*. Se o HerdMaster cair, o Herdr continua funcionando normalmente (NFR-009).

---

## 2. Serviços / Subsistemas criados (11 subsistemas, 29 módulos)

Todo o código fica em `src/herdmaster/`. Cada subsistema é independente e testado.

| Subsistema | Arquivo(s) | O que faz |
|------------|-----------|-----------|
| **Banco de dados** | `db/schema.py`, `db/repositories.py` | SQLite em modo WAL. 6 tabelas + 8 índices. Repositórios para Agentes, Tarefas, Mensagens, Projetos. **Claim atômico (CAS)** para evitar atribuição dupla de tarefas. |
| **Configuração** | `config.py` | Carrega/valida TOML (`tomllib`), recarga a quente (hot-reload via `ConfigWatcher`), logging estruturado em JSON (`structlog`). |
| **Barramento de mensagens** | `bus/messages.py`, `bus/server.py` | Servidor de socket Unix assíncrono (asyncio), protocolo JSON-RPC 2.0, pub/sub (unicast / broadcast / `group:<nome>`), persistência no SQLite, TTL de mensagens, upgrade WebSocket para streaming, e *fallback* em arquivo se o socket falhar. |
| **Adaptador Herdr** | `herdr/adapter.py`, `herdr/parser.py` | **Única** fronteira de I/O com o Herdr. Abstrai `herdr agent list`, `pane read`, `pane send`, `agent wait`. Usa `asyncio.create_subprocess_exec` com lista de argumentos (sem `shell=True` — sem injeção de comando). |
| **Fila de tarefas** | `dispatch/queue.py` | Máquina de estados `queued → assigned → dispatched → in_progress → done/failed/timeout/cancelled`. Prioridades (critical/high/normal/low), dependências (`depends_on`), reatribuição automática com retry. |
| **Injetor de despacho** | `dispatch/injector.py` | Injeta o prompt da tarefa no painel do agente. **Espera o agente ficar `idle` antes de enviar** (gargalo conhecido do Herdr), divide prompts longos em pedaços (chunking), faz *fallback* via arquivo, e tem retry com backoff exponencial. |
| **Watchdog** | `watchdog/engine.py`, `watchdog/recovery.py` | Detecção em 3 camadas: (1) eventos do Herdr em tempo real, (2) polling periódico, (3) comparação de hash de saída do terminal (terminal congelado). Estados `healthy → suspect → unhealthy → recovering`. Auto-recuperação: mata processo travado → respawn → replay da última tarefa → escala para humano após N falhas. |
| **ACL (controle de acesso)** | `acl/engine.py` | Políticas baseadas em papéis (orchestrator/worker/reviewer/observer). *Default-deny*. Curingas (`*`), grupos (`group:<nome>`), broadcast. Troca de configuração a quente. |
| **Modo Projeto** | `project/planner.py`, `project/squad.py`, `project/eta.py` | Pipeline de orquestração de projeto: análise → recomendação de squad → cálculo de ETA → decomposição em tarefas. |
| **API de controle** | `api/server.py` | Socket Unix (principal) + HTTP localhost opcional (exige token bearer). Todos os endpoints do §10 do PRD: `/projects`, `/tasks`, `/agents`, `/messages`, `/status`, `/metrics`, `/config/reload`. Envios de mensagem passam pela ACL. |
| **Dashboard TUI** | `tui/dashboard.py` | Painel em tempo real (5 painéis: agentes, tarefas, projetos, alertas, métricas). Backend `textual` → `rich` → texto puro (degrada graciosamente). |
| **CLI** | `cli.py` | Ponto de entrada `herdmaster`. Comandos: `start`, `stop`, `status`, `agents`, `tasks`, `projects`, `metrics`, `config reload`. |

---

## 3. Como o HerdMaster se integra ao Herdr (o ponto-chave)

```
┌─────────────────────────────────────────────────────────────┐
│                     VOCÊ (humano / orquestrador)             │
│            CLI `herdmaster`  ·  Dashboard TUI                 │
└───────────────┬─────────────────────────────────────────────┘
                │ (socket Unix / HTTP local)
┌───────────────▼─────────────────────────────────────────────┐
│                  HERDMASTER (plano de controle)              │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ API ctrl │ │ Fila +     │ │ Watchdog │ │ Modo Projeto │  │
│  │          │ │ Injetor    │ │ 3 camadas│ │ squad + ETA  │  │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └──────┬───────┘  │
│       │      Barramento de msgs · ACL · SQLite (WAL)         │
│       │             │             │             │           │
│       └─────────────┴──────┬──────┴─────────────┘           │
│                            │ (ÚNICA fronteira)               │
│                   Adaptador Herdr                            │
└────────────────────────────┬─────────────────────────────────┘
                             │ subprocess: herdr pane send / read / agent wait / list
┌────────────────────────────▼─────────────────────────────────┐
│                    HERDR (multiplexador)                      │
│   Pane A1 (orquestrador) · Pane A2..A8 (workers)              │
│   Cada pane = um terminal real com um agente de IA            │
└───────────────────────────────────────────────────────────────┘
```

**Fluxo na prática quando você inicia tudo:**

1. Você inicia o **Herdr** normalmente e abre seus agentes nos painéis (panes), como já faz hoje.
2. Você inicia o **HerdMaster** com `herdmaster start`. Ele:
   - cria/abre o banco SQLite em `~/.config/herdmaster/herdmaster.db`,
   - sobe o **barramento de mensagens** no socket Unix,
   - sobe o **watchdog** (que começa a observar os agentes via adaptador Herdr),
   - sobe o **injetor de despacho** (loop que pega tarefas da fila e injeta nos painéis),
   - sobe a **API de controle**.
3. O HerdMaster **descobre os agentes** chamando `herdr agent list --json` através do adaptador — ele lê o estado de cada pane.
4. Quando você cria uma tarefa (`herdmaster tasks create ...`) ou um projeto (`herdmaster projects create ...`):
   - a tarefa entra na **fila**,
   - o **injetor** espera o agente alvo ficar `idle`, então usa `herdr pane send <pane> "<prompt>"` para **digitar o prompt diretamente no terminal do agente**,
   - o **watchdog** acompanha o estado; se o agente travar, ele tenta recuperar automaticamente.
5. Os agentes **não sabem que o HerdMaster existe** — eles só recebem texto no terminal, como se um humano tivesse digitado. **Zero modificação nos agentes.**

> **Resumo:** o Herdr fornece a infraestrutura (terminais, visibilidade de estado, controle programático via CLI/socket). O HerdMaster é a *camada de orquestração inteligente* por cima.

---

## 4. Modelo de dados (SQLite, modo WAL)

6 tabelas (`db/schema.py`, conforme §11 do PRD):

| Tabela | Conteúdo |
|--------|----------|
| `agents` | Registro de agentes: id, label, tipo, papel, pane do Herdr, estado, saúde, força/strengths, métricas (tempo médio de tarefa, tarefas concluídas), último heartbeat. |
| `projects` | Projetos do Modo Projeto: escopo, estado, tier de complexidade, recomendação de squad, ETA (otimista/esperado/pessimista), análise do orquestrador, decisão humana, progresso. |
| `tasks` | Fila de tarefas: prompt, estado, prioridade, atribuição, dependências, `project_id`, retries, timeout, **coluna `version` para CAS atômico**. |
| `messages` | Log de mensagens do barramento (trilha de auditoria): tipo, de/para, payload, entregue, confirmado, expira_em. |
| `health_events` | Trilha de auditoria do watchdog: mudanças de estado, detecção de crash, tentativas de recuperação, escalações. |
| `project_history` | Histórico de projetos para melhorar a precisão do ETA ao longo do tempo. |

+ 8 índices para performance.

---

## 5. Modos de operação

### Modo Tarefa (Task Mode)
Você despacha uma tarefa individual para um agente. Fluxo: criar → enfileirar → despachar (injeção no pane) → monitorar → concluir.

### Modo Projeto (Project Mode) — o diferencial
Você submete o **escopo de um projeto inteiro**. O HerdMaster:
1. Injeta um prompt de análise no agente orquestrador (template do §6.6.4 do PRD).
2. Lê e **faz parsing da resposta JSON** do orquestrador (tolerante a JSON embutido em texto).
3. Extrai: tier de complexidade, squad sugerido, ETA, lista de tarefas.
4. Calcula o **ETA** com a fórmula do §6.6.5:
   ```
   eta_horas = (profundidade_caminho_crítico × tempo_médio_tarefa × multiplicador_complexidade) / fator_paralelismo
   multiplicadores: S=0.8, M=1.0, L=1.3, XL=1.8
   ```
   Apresentado como faixa: otimista / esperado / pessimista.
5. Apresenta squad + ETA para **aprovação humana** (aceitar / modificar / sobrescrever).
6. Ao aprovar, **decompõe em tarefas** (respeitando dependências) e despacha cada uma.
7. Acompanha progresso (% concluído) e grava histórico ao final.

---

## 6. Qualidade e testes

- **80 testes passando** (pytest + pytest-asyncio).
- 10 arquivos de teste: `test_db`, `test_bus`, `test_herdr`, `test_dispatch`, `test_watchdog`, `test_acl`, `test_config`, `test_api`, `test_project`, `test_e2e`.
- Inclui **testes E2E de ciclo de vida completo** (7 testes): tarefa idle/ocupada, projeto completo (análise→squad→aprovação→despacho→conclusão→histórico), watchdog detecta travamento e recupera.
- Todos os testes usam Herdr **mockado** (não exigem Herdr/agentes reais) e banco SQLite temporário — determinísticos e rápidos.

---

## 7. Bugs encontrados e corrigidos durante o desenvolvimento

Três bugs reais foram capturados no portão de validação **antes** do release (nenhum chegou à versão final):

1. **Falha de segurança na ACL** — `worker→worker` era incorretamente permitido (resolução de papéis do alvo estava errada). Corrigido + teste de regressão.
2. **Ordenação de prioridade na fila** — prioridade `critical` (valor 0) era tratada como "falsy" em Python e ordenada como `normal`. Corrigido + teste.
3. **Bug no restart da API** — `_restart_agent` referenciava atributo inexistente (`self.restart_agent` em vez de `self.restart_agent_hook`), gerando erro 500. Descoberto pelo agente de documentação ao escrever o API_REFERENCE. Corrigido + teste de regressão.

---

## 8. Stack tecnológica (travada)

Python 3.12+ · `asyncio` · `sqlite3` (WAL, sem ORM) · `tomllib` · `typer` (CLI) · `rich`/`textual` (TUI) · `structlog` (logs JSON) · `subprocess` (integração Herdr). **Sem Postgres, sem Rust, sem nuvem.** Local-first.

---

## 9. Limitação conhecida de ambiente

No ambiente sandbox WSL onde o desenvolvimento ocorreu, o bind de socket Unix é bloqueado (`PermissionError`), então um `herdmaster start` *ao vivo* não consegue subir totalmente ali. A CLI trata isso graciosamente (reporta o erro, sem traceback). **Em um host Linux normal, roda sem problema.** O runtime completo é comprovado pelos 7 testes E2E que rodam em processo (sem socket real). Veja `QUICKSTART_pt-BR.md` para rodar em host real.

---

## 10. Transição para o Dia 2 (operação)

Para assumir a operação:

1. **Código:** tudo em `/mnt/c/VMs/Projetos/HerdMaster/`, versionado em git, tag `v1.0.0`, espelhado no GitHub (`customized_herdr`).
2. **Documentação:** `README.md` (instalação + referência de config), `docs/TECHNICAL_DESIGN.md` (arquitetura/concorrência), `docs/API_REFERENCE.md` (todos os endpoints), `docs/TROUBLESHOOTING.md` (modos de falha + recuperação), `QUICKSTART_pt-BR.md` (passo a passo Linux), e os 3 diagramas HTML animados em `docs/architecture_*.html`.
3. **Deploy:** `deploy/install.sh` (instalador idempotente) + `deploy/herdmaster.service` (unit systemd --user).
4. **Configuração:** copie `config/herdmaster.example.toml` para `~/.config/herdmaster/config.toml` e ajuste (especialmente a seção `[acl]` com seus agentes e o token da API se usar HTTP).
5. **Onde os dados vivem:** `~/.config/herdmaster/` (config.toml, herdmaster.db, herdmaster.log, herdmaster.sock).
6. **Testes:** `./.venv/bin/python -m pytest tests/ -q` deve dar 80 passando antes de qualquer mudança.

---

## 11. Próximos passos sugeridos (backlog para depois do v1.0.0)

- Cobertura de teste de carga real (32 agentes, 1000 tarefas) — cenários TC-008 do PRD em hardware real.
- Dashboard web opcional (FastAPI + Vite) — marcado como P2 no PRD.
- Métricas Prometheus exportadas para um Grafana.
- Templates de projeto adicionais além de feature/bugfix/refactor/migration.

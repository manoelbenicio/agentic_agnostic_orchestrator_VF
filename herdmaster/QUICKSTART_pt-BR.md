# HerdMaster v1.0.0 — Quickstart e Sessão Ao Vivo (Linux)

> Guia passo a passo para rodar o HerdMaster em um **host Linux real** (fora do sandbox),
> ver os serviços subindo e demonstrar as funcionalidades trabalhando juntas.
> Idioma: Português (Brasil).

---

## Pré-requisitos

- **Linux** (ou WSL2 com permissão de bind de socket Unix) — em sandbox restrito o bind falha.
- **Python ≥ 3.12** (`python3 --version`)
- **Herdr** instalado e no `PATH` (`herdr --version`) — necessário para uso *real*; para a demo
  em processo (testes), não é preciso Herdr real.
- `git`

---

## 1. Obter o código

```bash
git clone https://github.com/manoelbenicio/customized_herdr.git
cd customized_herdr
```

## 2. Criar ambiente virtual e instalar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"     # instala typer, rich, structlog + pytest (dev)
```

## 3. Verificar a instalação

```bash
herdmaster --help            # deve listar: start, stop, status, agents, tasks, projects, metrics, config
python -m herdmaster --help  # equivalente
```

## 4. Rodar a suíte de testes (prova que tudo funciona)

```bash
python -m pytest tests/ -q
# Esperado: 80 passed
```

> Os testes usam Herdr **mockado** e banco temporário, então passam em qualquer máquina,
> mesmo sem Herdr instalado. Esta é a melhor forma de validar a instalação.

## 5. Configurar

```bash
mkdir -p ~/.config/herdmaster
cp config/herdmaster.example.toml ~/.config/herdmaster/config.toml
$EDITOR ~/.config/herdmaster/config.toml
```

Ajuste principalmente:
- **`[paths]`** — onde ficam db/socket/log (padrão: `~/.config/herdmaster/`).
- **`[acl]` / `[[acl.roles]]`** — defina seus agentes e papéis. Ex.: o agente orquestrador
  (`A1`) com papel `orchestrator` e os workers (`A2`..`A8`) com papel `worker`.
- **`[api]`** — `bind = "127.0.0.1"`; se for usar o modo HTTP, defina um `token` (obrigatório).
- **`[watchdog]`** — `soft_timeout_s` < `hard_timeout_s`, `poll_interval_s`.

## 6. Iniciar o plano de controle (host real)

Em um terminal (com o Herdr já rodando seus agentes em panes):

```bash
herdmaster start
```

O que sobe, na ordem:
1. Config + logging (JSON) carregados
2. Banco SQLite inicializado em `~/.config/herdmaster/herdmaster.db` (modo WAL)
3. **Barramento de mensagens** no socket `~/.config/herdmaster/herdmaster.sock`
4. **Watchdog** começa a observar os agentes via adaptador Herdr
5. **Injetor de despacho** (loop de fila → pane)
6. **API de controle** (socket Unix; HTTP local se habilitado)

Encerramento limpo com `Ctrl+C` (SIGINT) ou `SIGTERM`.

> Se você vir `PermissionError: Operation not permitted` no bind do socket, você está em um
> ambiente restrito (sandbox). Rode em um host Linux normal ou WSL2 com permissões adequadas.

## 7. Operar (em outro terminal)

```bash
herdmaster status                 # saúde + uptime do plano de controle
herdmaster agents                 # lista agentes e estados (lidos do Herdr)
herdmaster tasks list             # tarefas na fila
herdmaster metrics                # KPIs (tarefas/agente, tempo médio, taxa de falha)
```

---

## 8. Sessão ao vivo — demonstração das funcionalidades juntas

### Cenário A — Despacho de tarefa individual (Modo Tarefa)

```bash
# Cria uma tarefa e atribui a um agente worker (ex.: A2)
herdmaster tasks create \
  --title "Implementar endpoint de login" \
  --prompt "Implemente POST /login com JWT conforme docs/spec.md" \
  --assign A2 --priority high

herdmaster tasks list             # veja a tarefa em 'queued' → 'dispatched' → 'in_progress'
```

O que acontece por baixo:
1. A tarefa entra na **fila** (`queued`).
2. O **injetor** espera o agente `A2` ficar `idle` (via `herdr agent wait`).
3. Quando idle, injeta o prompt no pane do A2 (`herdr pane send`) — o agente recebe o texto
   como se você tivesse digitado.
4. O **watchdog** acompanha; se o A2 travar, tenta recuperar e re-despachar.

### Cenário B — Projeto completo (Modo Projeto)

```bash
herdmaster projects create \
  --name "Sistema de Autenticação" \
  --scope "Construir auth completo: JWT, OAuth2 (Google/GitHub), RBAC, reset de senha, \
           verificação de email. Inclua endpoints, middleware, migrações e testes." \
  --deadline "2026-06-25T18:00:00Z"
```

O HerdMaster então:
1. Injeta um **prompt de análise** no agente orquestrador.
2. Faz **parsing do JSON** retornado (tier de complexidade, squad, ETA, tarefas).
3. Calcula o **ETA** (faixa otimista/esperado/pessimista).
4. Mostra a recomendação para sua **aprovação**:

```bash
herdmaster projects list                  # veja o projeto em 'awaiting_approval'
# Inspecione a sugestão de squad + ETA, então aprove:
herdmaster projects approve <project_id>
```

5. Ao aprovar, o projeto é **decomposto em tarefas** (respeitando dependências) e cada uma é
   despachada automaticamente para os agentes do squad.
6. Acompanhe o progresso:

```bash
herdmaster projects list          # % concluído sobe conforme as tarefas terminam
herdmaster metrics
```

### Cenário C — Dashboard em tempo real (TUI)

```bash
python -c "from herdmaster.tui.dashboard import DashboardApp; DashboardApp.from_config().run()"
```

Mostra 5 painéis ao vivo:
- **Agentes**: id, tipo, estado, saúde, tarefa atual, uptime, último heartbeat
- **Tarefas**: estado + prioridade + responsável
- **Projetos**: barras de progresso + ETA ao vivo
- **Alertas**: escalações do watchdog
- **Métricas**: tarefas/agente, tempo médio, taxa de falha

### Cenário D — Watchdog recuperando um agente travado

Não precisa de ação manual: se um agente fica em `working` além do `hard_timeout` sem mudança
de saída no terminal, o watchdog:
1. marca `suspect` → `unhealthy`,
2. mata o processo travado e faz **respawn** no pane,
3. espera ficar `idle` e **re-injeta a última tarefa**,
4. após N falhas consecutivas, emite um **alerta de escalação** (visível no dashboard e no log).

---

## 9. Rodar como serviço systemd (opcional, recomendado)

```bash
bash deploy/install.sh           # idempotente: cria config, instala unit systemd --user
systemctl --user daemon-reload
systemctl --user enable herdmaster
systemctl --user start herdmaster
systemctl --user status herdmaster
journalctl --user -u herdmaster -f   # logs ao vivo (JSON estruturado)
```

---

## 10. Onde ficam as coisas

```
~/.config/herdmaster/
├── config.toml          # sua configuração (NÃO versionar — contém tokens)
├── herdmaster.db        # banco SQLite (WAL)
├── herdmaster.log       # log estruturado JSON
└── herdmaster.sock      # socket Unix do plano de controle
```

---

## 11. Observabilidade (Prometheus + Grafana)

Para visualizar o comportamento da API, tempo de execução das tarefas, consumo de CPU e bloqueios durante os *Heavy Workloads*, você pode subir a stack de Observabilidade via Docker:

```bash
cd deploy/observability
docker compose up -d
```

Acesse no seu navegador:
- **Prometheus:** `http://localhost:9090`
- **Grafana:** `http://localhost:3000` (Login: `admin` / `admin`)

---

## 12. Solução de problemas

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| `PermissionError` no bind do socket | Ambiente sandbox restrito | Rode em host Linux/WSL2 normal |
| `CLI not yet built` ao `python -m herdmaster` | Pacote não instalado em modo editável | `pip install -e .` |
| `herdmaster status` diz que não está rodando | Plano de controle não iniciado | `herdmaster start` em outro terminal |
| Agente não recebe o prompt | Agente não estava `idle`; prompt muito longo | O injetor já espera idle + faz chunking/fallback em arquivo; verifique `herdmaster agents` |
| Mensagem rejeitada entre agentes | Política ACL negou | Ajuste `[[acl.roles]]` em `config.toml` |

Mais detalhes em `docs/TROUBLESHOOTING.md`. Diagramas de arquitetura em
`docs/architecture_macro.html`, `architecture_micro.html`, `architecture_deep.html`
(abra no navegador — são autocontidos, funcionam offline).

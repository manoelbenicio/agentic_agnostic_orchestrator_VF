# 🛠️ Guia de Operações — Agnostic Orchestration Platform (AOP)
**Versão:** 1.0.0 (2026-06-26) | **Status:** Homologado para o Time de Day-2 (pt-BR)

Este guia fornece instruções completas sobre a arquitetura, navegação, operação, observabilidade, segurança e troubleshooting da **Agnostic Orchestration Platform (AOP)**. Todo o conteúdo foi fundamentado diretamente na inspeção física do código-fonte real do frontend, backend, scripts de operações e stack de monitoramento.

---

## 1. Visão Geral da Plataforma

A **Agnostic Orchestration Platform (AOP)** é uma superfície de controle unificada para orquestração de squads de agentes de inteligência artificial autônomos. A plataforma suporta execução local-first, isolamento de execução baseado em Seats dedicados por provedor/tenant, controle rígido de comunicação entre agentes e telemetria fina de custos (FinOps) e depuração (Tracing).

### Arquitetura de Integração (L1 a L4)

- **L1 — Camada Física / Host:** Máquina servidora (ou WSL2 no ambiente de desenvolvimento local) contendo os runtimes nativos dos agentes (CLIs como `kiro`, `codex`, `gemini` mapeado para `agy`).
- **L2 — Camada de Execução e Isolamento (Herdr / Seat Pool):** Gerencia processos isolados e multiplexação de terminais (panes do `Herdr`). Controla a alocação de licenças de API via tokens injetados temporariamente no ambiente isolado (`home_dir` específico de cada Seat).
- **L3 — Camada de Controle e barramento (HerdMaster):** Controla o fluxo de tarefas (tasks), filas de mensagens assíncronas (Message Bus), auditoria de segurança (ACL de topologia) e recuperação ativa de agentes (Watchdog).
- **L4 — Camada de Superfície AOP (Control-Plane & Web UI):** Oferece a API agregadora REST/WebSocket, expõe métricas Prometheus e apresenta a interface web moderna construída com React/Next.js.

```
+-------------------------------------------------------------+
|                        AOP Web UI                           |
|                    (Porta local: 13000)                     |
+------------------------------+------------------------------+
                               |
                               | HTTP / WebSockets
                               v
+-------------------------------------------------------------+
|                     AOP Control-Plane                       |
|                     (Porta local: 8090)                     |
+---+--------------------------+--------------------------+---+
    |                          |                          |
    | Postgres (5432)          | Redis (6379)             | HTTP + Bearer Token
    v                          v                          v
+---+--------------------------+--------------------------+---+
|                Banco de Dados & Cache                       |  +--------------------+
|                (Snapshots & FinOps)                         |  |     Observability  |
+-------------------------------------------------------------+  |   Prometheus (9090)|
                               |                                 |   Grafana (3000)   |
                               | HTTP / Socket Queue             |   Alertmgr (9093)  |
                               v                                 |   Webhook (9099)   |
+-------------------------------------------------------------+  +---------^----------+
|                     HerdMaster Engine                       |            |
|                    (Porta local: 8080)                      +------------+
+------------------------------+------------------------------+
                               |
                               | Unix Socket / CLI command
                               v
+-------------------------------------------------------------+
|                        Herdr Runtime                        |
|                    (Multiplexador Terminais)                |
+-------------------------------------------------------------+
```

### Componentes e Portas de Rede

A tabela a seguir lista todos os componentes e portas expostos pelo ecossistema AOP:

| Componente | Porta | Protocolo | Tipo de Acesso | Descrição |
| :--- | :--- | :--- | :--- | :--- |
| **Postgres** | `5432` | TCP (SQL) | Interno | Banco de dados relacional para snapshots de topologia, agentes e FinOps. |
| **Redis** | `6379` | TCP (Redis) | Interno | Cache de estados e enfileiramento temporário. |
| **HerdMaster API** | `8080` | TCP (HTTP) | Interno (com Token) | Backend de orquestração HerdMaster (/status, /metrics, /tasks). |
| **AOP Control-Plane** | `8090` | TCP (HTTP/WS) | Público | API agregadora da plataforma (usada pela UI). |
| **Prometheus** | `9090` | TCP (HTTP) | Público / Interno | Coleta e armazenamento de métricas do sistema. |
| **Alertmanager** | `9093` | TCP (HTTP) | Público / Interno | Recebimento e roteamento de alertas gerados pelo Prometheus. |
| **Remediation Webhook** | `9099` | TCP (HTTP) | Interno | Webhook que limpa agentes fantasmas (não listados) no DB do HerdMaster. |
| **Grafana** | `3000` | TCP (HTTP) | Público | Visualização de painéis analíticos (FinOps, Tracing). |
| **AOP Web UI** | `13000` | TCP (HTTP) | Público | Interface Web do usuário. |

---

## 2. Acesso e Navegação

O acesso principal para o operador de Day-2 é feito através do navegador na URL de frontend:
- **AOP Web UI:** [http://127.0.0.1:13000](http://127.0.0.1:13000)

### Elementos do Header (Cabeçalho)
O Header da aplicação é fixo e contém os seguintes componentes da esquerda para a direita:
1. **Identificação da Plataforma:**
   - Título principal: `Agnostic Orchestration Platform`
   - Subtítulo explicativo: `HerdMaster + Herdr runtime foundation`
2. **HealthBadge (Status da API):**
   - Um botão interativo que exibe o status de acoplamento com o backend.
   - **Indicadores Visuais:**
     - *Checking...* (Ícone de recarga girando - `RefreshCw`): Carregando o estado.
     - *API ok* (Ícone verde - `CheckCircle`): Backend e acoplamento com HerdMaster operacionais.
     - *API offline* (Ícone vermelho - `XCircle`): Indica que a API no IP:Porta `8090` está inacessível.
   - *Ação:* Clicar no badge força uma nova consulta de saúde (`refetch`).
3. **ThemeToggle (Seletor de Tema):**
   - Toggle visual para mudar a aparência da aplicação entre os modos **Light**, **Dark** ou sincronizar com o **System** (padrão do SO).

### Elementos do Menu Lateral (Sidebar)
O menu lateral esquerdo permite alternar entre as telas principais da aplicação:
- **Dashboard:** Visão consolidada de recursos e custos ativos (página inicial `/`).
- **Squad Builder:** Canvas interativo baseado na biblioteca `@xyflow/react` para edição de topologia (`/squad-builder`).
- **Live Panel:** Tela para monitoramento em tempo real via WebSockets (`/live`).
  > **Nota de UI:** O item *Live Panel* possui um ponto indicador pulsante verde (`ml-auto size-2 animate-pulse rounded-full bg-success`) sinalizando a disponibilidade de conexão em tempo real.

---

## 3. Dashboard

O Dashboard centraliza as informações geradas dinamicamente pelos endpoints `/agents`, `/seats` e `/finops/projects/{tenant_id}/{project_id}/rollup` da API do Control-Plane.

### Cards Superiores
- **Agents:** Mostra a quantidade de runtimes de agentes ativamente registrados no painel. O rodapé do card indica `"registered runtimes"` (ou `"no agents registered"` se vazio).
- **Seats:** Indica a proporção de licenças ativas do Seat Pool (exemplo: `"3/4 leased"`). Informa quantos Seats estão em uso concorrente.
- **Project Cost:** Custo acumulado do projeto padrão (`tenant-a` / `project-a`) formatado em USD (ex: `$0.0050`). O rodapé exibe o número total de registros de uso associados.
- **Runtime Burn:** Mostra a quantidade de entradas de agentes no registro do control-plane cujo status não é `"removed"`.

### Execution Modes (Modos de Execução)
No painel do lado direito, são descritos os modos de execução suportados pelo motor:
1. **Terminal Mode (Herdr Panes):** Os comandos e diálogos rodam em terminais multiplexados interativos locais (panes Herdr). Útil para depuração visual manual ou execução local direta.
2. **Socket Mode (Fila/HerdMaster):** Os agentes consomem tarefas de maneira autônoma consumindo de uma fila REST/HTTP gerenciada pelo HerdMaster. O ciclo de vida da tarefa é monitorado remotamente sem necessidade de interface de terminal aberta.
3. **Visual Builder (Canvas):** Utilização do editor de topologia para desenhar canais de comunicação e ACLs de segurança das mensagens.

### Painéis Inferiores
- **Agents Registry (Tabela / Grid):** Lista cada agente registrado com seu ID abreviado, Nome/Label, Função (Role), Provedor (Vendor) e Status de Conexão.
  - *Cores de Provedores:* Cada bloco do provedor tem cores estilizadas baseadas em gradiente CSS:
    - *OpenAI:* Verde (`from-emerald-500/20 to-teal-500/20`)
    - *Anthropic:* Laranja (`from-amber-500/20 to-orange-500/20`)
    - *Google:* Azul (`from-blue-500/20 to-indigo-500/20`)
    - *Meta:* Roxo (`from-purple-500/20 to-violet-500/20`)
  - *Status do Agente:*
    - `active` (Ponto verde pulsante)
    - `idle` (Ponto cinza)
    - `offline` (Ponto vermelho)
- **Seat Pool (Tabela / Grid):** Lista todos os assentos lógicos criados para o tenant. Cada card exibe o identificador único do Seat, o provedor, o status de leasing (`ref_count > 0` = ponto verde/leased; ou ponto cinza/available).
- **FinOps Panel:** Exibe a segmentação fina dos custos:
  - **Total Cost:** Soma acumulada geral em USD.
  - **Token Cost:** Custos atrelados ao consumo de LLM tokens (entrada/saída multiplicados pelos preços definidos).
  - **Seat Cost:** Custos atrelados ao tempo de ocupação de Seats isolados por segundo.
  - **Records:** Contagem total de transações de billing processadas.

---

## 4. Squad Builder (Canvas de Topologia)

O **Squad Builder** permite desenhar a topologia de rede que define quem pode se comunicar com quem. O backend mapeia esse grafo e gera ACLs (Access Control Lists) rígidas que o HerdMaster valida em tempo de execução na rota `/squads/{squad_id}/messages`.

### Regras de Topologia Rígidas (ACL)
1. **Regra Padrão (Default Policy):** `deny` (toda comunicação é negada por padrão).
2. **Papel do Tech-Lead (orchestrator):** Possui permissão para despachar e reatribuir tarefas (`can_dispatch_tasks=true`, `can_reassign_tasks=true`). O Tech-Lead pode falar com todos os agentes conectados a ele por um edge.
3. **Comunicação Hub-and-Spoke:** Workers (agentes de execução) **NÃO** podem iniciar conversas com outros workers diretamente sem que exista uma conexão explícita ligando-os no canvas. Se tentarem, o backend bloqueia a mensagem retornando `HTTP 403 Forbidden` com código `topology_violation`.
4. **Isolamento de Workers:** Um nó worker que não possua conexões será considerado inválido pela camada de validação do backend (`TopologyValidator`), impedindo a gravação do snapshot com o erro: `Invalid topology: worker <agent_id> is unreachable`.

### Passo a Passo: Criação e Gravação de Squads

1. **Acessar a Tela:** Navegue até o item **Squad Builder** no menu lateral.
2. **Identificar Agentes Não Alocados:** Na barra de ferramentas superior (*Toolbar*), os agentes registrados no sistema que ainda não foram colocados no Canvas são listados sob a etiqueta `"Add agent:"`.
3. **Adicionar Agente no Canvas:** Clique no botão com o nome do agente desejado (ex: `+ w6:p1`). Ele aparecerá em uma posição aleatória no Canvas como um nó móvel.
4. **Criar Conexões (Edges):** Clique com o mouse na saída (handle) de um nó de origem e arraste até a entrada do nó de destino. Isso define um canal de comunicação direcionado e autorizado.
5. **Ajustar Papeis:**
   - ⚠️ *sem UI ainda (gap):* Não há botão visual para alternar o papel (role) de um agente entre `orchestrator` e `worker` diretamente no canvas. O papel é herdado da base de registro de agentes (`Agent Registry`) de forma automática.
6. **Salvar Topologia:** Clique no botão **Save Topology** no canto superior direito.
   - O botão exibirá estados visuais durante o salvamento:
     - `Saving...` com um spinner ativo (`Loader2`).
     - `Saved!` (verde) após sucesso de envio para o endpoint `/squads/default/topology`.
     - `Save failed` (vermelho) caso ocorra algum erro na comunicação ou validação de regras de conectividade.
7. **Editar/Ajustar:** Arraste os nós conforme necessário e crie novas conexões. Em seguida, clique novamente em **Save Topology** para atualizar.
8. **Excluir Conexão/Agente:**
   - Para deletar uma linha de conexão, selecione a linha no Canvas e aperte a tecla `Backspace` ou `Delete`.
   - ⚠️ *sem UI ainda (gap):* Não há botão na interface web para remover um nó de agente do canvas (a exclusão do nó de agente requer recarregar a página ou reconfigurar via API).

---

## 5. Projects
⚠️ **Totalmente sem UI ainda (gap)**

O conceito de **Projects** na AOP serve para correlacionar custos (FinOps) e eventos de trace a objetivos corporativos e issues de desenvolvimento.

### Operação via API (Alternativa ao GAP de UI)
Como não existe uma tela de CRUD de projetos, os operadores devem interagir diretamente com a API do control plane ou através do fluxo de metadados das tarefas. A especificação do `project_id` e do `tenant_id` é passada de forma dinâmica como parâmetros das requisições de criação de tasks e rastreamento.

#### Associação de Projetos a Tasks/Issues
As chaves `project_id`, `tenant_id` e `issue_id` são atributos exigidos no payload do endpoint de criação de tarefas (`POST /tasks`) e no log de custos.

Exemplo de associação utilizando o `curl`:
```bash
curl -X POST http://127.0.0.1:8090/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-manutencao-101",
    "tenant_id": "tenant-a",
    "project_id": "projeto-automacao-b",
    "issue_id": "issue-4422",
    "assignee_runtime": "w6:p1",
    "prompt": "Executar auditoria de pacotes e relatar vulnerabilidades.",
    "operation_mode": "socket",
    "seat_seconds": 120
  }'
```

---

## 6. Tasks
⚠️ **Criação e Gestão sem UI ainda (gap)**

A interface web da AOP é focada em Dashboard, Canvas de Topologia e Live Tracing. O ciclo de vida e agendamento de tarefas devem ser executados através da API ou CLI do HerdMaster.

### Ciclo de Vida da Task
Toda tarefa criada passa pelo seguinte fluxo de estados gerenciado pelo control-plane:
1. **Queued (Em Fila):** A tarefa é registrada no control-plane ou enviada ao HerdMaster e aguarda o agente assignee reivindicá-la.
2. **Claimed (Reivindicada):** O runtime do agente correspondente detecta a atribuição e remove a tarefa da fila de pendentes.
3. **Running (Executando):** O executor executa o prompt do agente e monitora sua evolução em tempo de execução.
4. **Blocked (Bloqueada):** O watchdog ou o próprio runtime sinaliza que o agente está aguardando recursos externos, tokens esgotados ou travamento.
5. **Done (Concluída):** Tarefa concluída com sucesso. Recursos lógicos (Seats) são liberados para o pool.
6. **Failed (Falhou):** Erro interno, timeout estourado pelo watchdog ou falha explícita no script do agente.

### Criação e Despacho de Tarefa (Exemplo via Curl)
A API expõe o endpoint `/tasks` (porta `8090`) para despacho imediato:
```bash
curl -X POST http://127.0.0.1:8090/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-day2-test-01",
    "tenant_id": "tenant-a",
    "project_id": "project-a",
    "assignee_runtime": "w6:p1",
    "prompt": "Escrever relatório de auditoria de logs locais",
    "operation_mode": "terminal",
    "seat_seconds": 60
  }'
```

---

## 7. Live Panel / Monitoramento de Traces

O **Live Panel** (`/live`) permite aos engenheiros de Day-2 monitorar a execução interna dos agentes em tempo real via streaming por WebSocket (com fallback automático para pooling HTTP em caso de instabilidade na rede).

### Funcionalidades do Painel de Visualização
1. **Seletor de Agentes:** Permite selecionar múltiplos agentes em paralelo clicando nos botões de tag. A tela exibe um painel de tracing dedicado para cada agente marcado.
2. **Stream de Eventos:** Exibe a linha cronológica de transições internas do agente contendo:
   - **Camada (Layer):** `orchestration` (azul), `execution` (verde), `tool_use` (amarelo), `llm` (roxo), `system` (cinza).
   - **Sinal (Signal Type):**
     - `start` (Ícone de rádio - `Radio`)
     - `progress` (Ícone de onda - `Activity`)
     - `complete` (Ícone de raio - `Zap`)
     - `error` (Ícone de erro - `AlertCircle`)
     - `thought` (Ícone de cérebro - `Brain`): Representa o "Chain of Thought" (Cadeia de Pensamento) do agente.
   - **Token Burn:** Distintivo laranja (`🔥 X tok`) que exibe quantos tokens o modelo consumiu nessa transição de pensamento ou execução.
   - **Identificadores Finais:** ID resumido da Trace e identificador do runtime associado.
3. **Métrica Acumulada do Painel:**
   - No topo de cada painel de agente, um indicador cumulativo de consumo total de tokens é mostrado em tempo real (ex: `⚡ 1250 tok`).
   - Um ponto indicador colorido mostra o estado da conexão streaming:
     - **Verde Pulsante:** Conectado via WebSocket (`● LIVE`).
     - **Amarelo:** Operando via HTTP Polling (`● POLLING`).
     - **Vermelho:** Erro de conexão (`● OFFLINE`).

---

## 8. Observabilidade

A infraestrutura de observabilidade da AOP é executada em containers Docker Compose localizados em `HerdMaster/deploy/observability`.

### O que monitorar e Onde:

#### 1. Grafana
Acesso em [http://localhost:3000](http://localhost:3000) (credenciais padrão: `admin` / `admin`).
- **Dashboards Disponíveis:**
  - *HerdMaster Main:* Dashboard principal que reporta volumetria de tarefas, status dos agentes e integridade do registro.
  - *AOP FinOps:* Gráficos detalhados sobre custos cumulativos do projeto por tenant/vendor, taxas de burn de token por segundo e ocupação de Seats.
  - *AOP Tracing:* Cronologia de eventos de sistema estruturados por camadas L1-L4.

#### 2. Prometheus
Acesso em [http://localhost:9090](http://localhost:9090).
Armazena a série temporal de métricas coletadas dos endpoints `/metrics` (AOP Control-Plane) e `/metrics` (HerdMaster).

#### 3. Métricas Customizadas Importantes
- `aop_control_plane_up`: Liveness da API AOP (valor `1` = saudável).
- `herdmaster_whitelist_compliant`: Indica a conformidade com a lista de agentes autorizados (deve ser sempre `1`).
- `herdmaster_unlisted_agents_total`: Quantidade de agentes fantasmas ou não autorizados descobertos em execução (deve ser sempre `0`).
- `herdmaster_agents_total`: Total de agentes cadastrados no DB (atualmente `7` agentes canônicos).

#### 4. Endpoints de Health do Control Plane (Porta 8090)
- `GET /health`: Retorna a saúde geral com foco na conexão lógica de acoplamento com o HerdMaster.
  - Exemplo de resposta: `{"status": "ok", "coupling": {"status": "connected", "last_error": null}}`
  - **Fases do Coupling (`coupling.status`):**
    - `connected`: Acoplamento pleno e comunicação ativa por rede com HerdMaster.
    - `degraded`: Falha ao parear com o backend HTTP/Socket na inicialização. O sistema degrada para filas em memória mantendo a liveness geral.
    - `disconnected`: Queda abrupta de conectividade após boot estável.
- `GET /health/ready`: Valida as dependências físicas duras (Postgres e Redis). Se qualquer uma estiver indisponível, retorna `503 Service Unavailable`.
  - Exemplo de resposta: `{"status": "ready", "checks": {"postgres": true, "redis": true}, "coupling": {"status": "connected", "last_error": null}}`

#### 5. Alertmanager (Porta 9093) & Lista de Alertas
- **UnlistedAgentsDetected:** Dispara em 10 segundos se `herdmaster_unlisted_agents_total > 0`.
- **WatchdogSoftTimeoutLimit:** Dispara se um agente permanece em estado `suspect` por mais de `soft_timeout_s`.
- **WatchdogHardTimeoutLimit:** Dispara se o agente atinge `hard_timeout_s` em estado de travamento.
- **SeatPoolExhausted:** Dispara quando a fila de espera por Seats para um vendor ultrapassa o limite de tempo configurado.

---

## 9. Operações Day-2 (Manutenção de Rotina)

A execução, parada e expurgo de dados da infraestrutura devem seguir procedimentos rígidos baseados nos scripts localizados em `AOP/ops/`.

### 1. Inicialização do Stack
Execute o script para subir todos os containers Docker (Postgres, Redis, Prometheus, Grafana, Alertmanager) e inicializar os servidores Uvicorn/Next.js/HerdMaster:
```bash
bash AOP/ops/start.sh
```
*O que faz:*
1. Cria e valida as variáveis de ambiente baseadas no arquivo `AOP/deploy/.env`.
2. Sobe os containers de banco de dados e observabilidade.
3. Cria a configuração dinâmica do HerdMaster (`herdmaster.config.toml`) injetando a chave de API segura autogerada em `/tmp/aop-ops-runtime/herdmaster.token`.
4. Inicia o orquestrador HerdMaster (porta 8080) e o control plane (porta 8090).
5. Inicia o frontend (porta 13000) registrando os PIDs em `/tmp/aop-ops-run/`.

### 2. Parada do Stack
```bash
bash AOP/ops/stop.sh
```
*O que faz:*
1. Desliga o frontend, control-plane e processos HerdMaster enviando sinal de terminação ordenada (`SIGTERM`), seguido por `SIGKILL` em caso de recusa de parada em 20 segundos.
2. Para os containers de observabilidade (Prometheus/Grafana).
3. Para os containers de banco Postgres e cache Redis (preservando o volume físico dos dados).

### 3. Expurgo e Reinicialização Rápida (Flush & Restart)
```bash
bash AOP/ops/flush-restart.sh
```
*Funcionamento:*
1. Para todos os processos locais chamando o `stop.sh`.
2. Limpa os logs em `AOP/ops/logs/*` e exclui arquivos de PID temporários.
3. Exclui a pasta de prompts temporários (`/tmp/aop-ops-runtime/herdmaster/prompts`).
4. **Interação Destrutiva (Opcional):** O script solicitará que você digite `CONFIRMO`.
   - Se digitado `CONFIRMO`: dropa todos os schemas Postgres no banco de dados cujo prefixo seja `aop_`, executa `FLUSHALL` no Redis para limpar caches de fila, remove as tabelas públicas de mensagens, tasks e agentes do HerdMaster e reinicia o banco limpo.
   - Qualquer outra entrada: preserva o banco de dados e os dados de volume dos containers, limitando-se a reiniciar os processos.
5. Inicia o stack limpo chamando o `start.sh`.

### 4. Protocolo de Governança Check-In / Check-Out
Conforme a **Rule 6** estipulada em `AGENTS.md`, todo operador ou agente deve atualizar a tabela de histórico de manutenção em `checkin_checkout.md` no diretório raiz do projeto:
- **Antes de Iniciar:** Registrar CHECK-IN contendo Timestamp UTC, Nome do Agente, Task ID, e a lista exata de caminhos absolutos dos arquivos que serão modificados.
- **Após Finalizar:** Registrar CHECK-OUT contendo Timestamp UTC, arquivos que foram efetivamente alterados ou criados, status (COMPLETED ou FAILED), e evidência rastreável (ex: Hash SHA256 do arquivo ou resultado de testes bem-sucedidos).

### 5. Localização de Logs
Todos os arquivos de log de execução em tempo real das camadas operacionais residem no diretório:
- `AOP/ops/logs/`
  - `herdmaster.log`: Logs internos do orquestrador HerdMaster (JSON format).
  - `aop-control-plane.log`: Saída de depuração do Uvicorn e erros de rotas/Postgres/Redis.
  - `aop-frontend.log`: Logs de renderização do Next.js.

---

## 10. Troubleshooting

| Sintoma | Causa Comum | Ação Corretiva |
| :--- | :--- | :--- |
| **Header exibe "API offline" ou logs mostram "Failed to Fetch"** | O serviço do control-plane na porta `8090` está derrubado ou a configuração de CORS no backend rejeitou a requisição do navegador. | 1. Execute `ss -tlnp \| grep :8090` para ver se o processo Uvicorn está ouvindo.<br>2. Verifique se o `AOP_ENV_FILE` possui a propriedade `cors_origins` configurada corretamente.<br>3. Reinicie com `bash AOP/ops/start.sh`. |
| **Coupling Status retorna "degraded"** | Ausência da variável de ambiente `HERDMASTER_TOKEN` ou o orquestrador HerdMaster (porta `8080`) está desligado. | 1. Verifique se `/tmp/aop-ops-runtime/herdmaster.token` existe e possui a hash gerada.<br>2. Verifique os logs de inicialização do orquestrador em `ops/logs/herdmaster.log` para capturar possíveis falhas de permissão de bind ou token inválido. |
| **Processo trava acusando erro "database is locked"** | Concorrência de escrita no SQLite legado (HerdMaster). Ocorre tipicamente se um script externo (ex. webhook de remediação) abre transações manuais diretamente no arquivo `herdmaster.db` simultaneamente com o orquestrador. | 1. **Não acesse o SQLite diretamente por outros processos.** Toda operação de CRUD de agentes ou escrita de tarefas deve ser convertida em chamadas HTTP autenticadas direcionadas aos endpoints `/agents/{id}` da API REST.<br>2. Se o banco permanecer bloqueado após travamentos, force a limpeza do WAL rodando: `sqlite3 ~/.config/herdmaster/herdmaster.db "PRAGMA wal_checkpoint(TRUNCATE);"` seguido por `rm -f ~/.config/herdmaster/herdmaster.db-wal`. |
| **HerdMaster retorna HTTP 401 Unauthorized na porta 8080** | O control-plane AOP tentou acessar a API do HerdMaster enviando um token incorreto ou ausente no header de autenticação. | 1. Verifique se o script `start.sh` recuperou com sucesso o token dinâmico através do método `herdmaster_token()`.<br>2. Certifique-se de que a variável de ambiente `HERDMASTER_TOKEN` está devidamente exportada antes do Uvicorn iniciar. |
| **Mensagem bloqueada com erro "topology_violation"** | Dois agentes marcados como `worker` tentaram enviar mensagens diretamente entre si sem ter um elo de conexão (edge) configurado e ativo no Canvas da Topologia. | 1. Acesse o **Squad Builder** via UI.<br>2. Desenhe um canal de conexão que conecte o agente transmissor ao agente receptor.<br>3. Clique em **Save Topology** para registrar a nova política de ACL no Postgres. |

---

## 11. Segurança, Autenticação e Isolamento

### OAuth Device Login (Fluxo de Credenciais)
Os agentes utilizam credenciais do provedor (CLI) ativas no host. O sistema segue o paradigma de **autenticação prévia no Host**:
1. O operador executa o login interativo no navegador a partir do host para cada CLI utilizada (`codex` para OpenAI, `gemini`/`agy` para Google, `kiro auth login` para Kiro).
2. As pastas locais contendo as chaves e tokens de sessão (`~/.codex`, `~/.kiro`, `~/.gemini`) são montadas como diretórios compartilhados de **apenas leitura (Read-Only)** no container Docker AOP.
3. O backend CAO escaneia esses subdiretórios mapeados e realiza a auto-descoberta dos tokens ativos, alimentando a API sem expor ou gerenciar chaves brutas de segurança na interface frontend.

### Isolamento de Execução dos Seats
- **Isolamento de Diretório:** Cada `Seat` ativo no pool de recursos é instanciado com uma pasta de trabalho exclusiva (`home_dir` - ex: `/tmp/aop-seat-codex`).
- **Isolamento de Variáveis:** Ao despachar um subprocesso de agente em um Seat alocado, o control-plane limpa o ambiente e expõe apenas as variáveis fornecidas pelo método `get_env()` do assento:
  ```bash
  HOME=<home_dir_do_seat>
  SEAT_ID=<seat_id>
  VENDOR=<provedor>
  TENANT_ID=<tenant_id>
  SEAT_TOKEN=<token_de_sessao_curto>
  ```
  Isso impede vazamentos cruzados de cache, histórico de comandos e tokens persistentes entre tenants.

### Seat Affinity (Afinidade de Assentos para Subagentes)
Quando um agente principal aluga um Seat do pool para executar uma tarefa complexa e decide delegar tarefas menores gerando um **Subagente**, o sistema não consome um novo Seat físico do pool de licenças. Ele aplica afinidade herdando as credenciais e incrementando a contagem de referência (`ref_count`) no mesmo Seat, liberando-o apenas quando todos os subagentes terminarem a execução.

---

## 12. Glossário

- **Herdr:** Motor multiplexador local que registra e gerencia as panes de terminal virtuais onde os scripts de agentes rodam interativamente.
- **HerdMaster:** Orquestrador central encarregado da segurança de rede (ACL), barramento de comunicação assíncrona, fila de tasks e watchdog.
- **Seat (Assento):** Unidade lógica de recurso associada a um provedor e inquilino (tenant). Fornece isolamento e mapeia o limite de concorrência contratado por assinaturas.
- **Tech-Lead:** Agente orquestrador principal de um Squad (identificado no DB pelo papel `orchestrator`). Possui autoridade para despachar, delegar ou reatribuir tarefas. Não recebe prompts de tarefas diretas.
- **Topologia / ACL:** Grafo estruturado de conexões que determina as restrições de tráfego de mensagens entre os agentes.
- **Coupling (Acoplamento):** Grau de conectividade operacional entre as camadas do AOP Control-Plane e do HerdMaster. Pode ser *connected*, *degraded* ou *disconnected*.
- **Executor Terminal:** Roteador de execução de tarefa focado em interatividade local em panes Herdr.
- **Executor Socket:** Roteador focado em tarefas assíncronas em segundo plano integradas diretamente nas filas controladas via endpoints REST do HerdMaster.
- **FinOps Dual:** Metodologia de contabilidade de nuvem integrada na AOP que monitora e quantifica custos baseando-se simultaneamente no consumo de LLM tokens e tempo de locação (segundos) de Seats.

---

## 13. Tabela Geral de Gaps de UI Conhecidos

A tabela abaixo compila todas as capacidades operacionais e funcionais que existem apenas sob a API ou CLI, não possuindo representação visual ou controles interativos na interface Web:

| Área | Feature / Capacidade | Descrição do Gap de UI | Solução / Contorno Operacional |
| :--- | :--- | :--- | :--- |
| **Projects** | CRUD de Projetos | Não existe página para cadastrar, editar ou deletar projetos na interface do usuário. | Enviar dados de `project_id` e `tenant_id` como metadados nos payloads JSON da API. |
| **Tasks** | Criação e Despacho de Tarefas | A interface do usuário não possui campos ou painéis para criação de novas tarefas ou escolha de modo de operação (`terminal` x `socket`). | Chamar o endpoint `POST /tasks` via `curl` ou utilizar o binário CLI `herdmaster tasks create`. |
| **Visual Builder** | Edição de Papeis (Roles) | Não há controles ou botões contextuais no Canvas para redefinir o papel de um nó de agente (ex: torná-lo Tech-Lead ou Worker). | Executar um comando SQL `UPDATE agents SET role='...' WHERE id='...'` no banco `herdmaster.db`. |
| **Visual Builder** | Exclusão Física de Agentes | O Canvas do React Flow permite desconectar edges, mas não possui botão ou painel lateral para deletar um nó de agente fisicamente da tela de trabalho sem recarregar a página. | Remover o agente da base de dados através da rota `DELETE /agents/{id}` da API REST. |
| **Credentials** | Gestão de Sessões OAuth | Não existe a tela de "Sessions" na Web UI para login inicial via fluxo Device OAuth ou revogação de tokens de provedores. | Executar comandos de autenticação na máquina Host (`kiro auth login`, `codex`, `gemini`) e reiniciar o stack. |
| **Seats** | Provisionamento de Seats | A interface Web apenas lista o Seat Pool ativo de forma informativa. Não há botão para registrar novos Seats na plataforma. | O registro é feito de forma programática através do arquivo de configuração do control-plane (`dependencies.py`). |

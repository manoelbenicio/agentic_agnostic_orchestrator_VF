# HerdMaster CLI: Guia de Referência de Comandos

O `herdmaster` é um utilitário de linha de comando (CLI) construído em Python (utilizando a biblioteca Typer). Você está perfeitamente correto: ele é essencialmente um "client" (uma casca) que formata e envia chamadas HTTP ou via Unix Socket para a API de Controle do HerdMaster (que roda em background).

Abaixo estão todos os comandos disponíveis no sistema, divididos por categoria.

---

## 1. Comandos de Ciclo de Vida (Daemon)

Esses comandos controlam o próprio processo do orquestrador (Control Plane).

* **`herdmaster start`**
  * **O que faz:** Inicializa o Control Plane no modo *foreground* (preso no terminal). Ele sobe o Banco SQLite, a Fila, o Watchdog, o Socket e a API.
  * **Opções úteis:**
    * `--http`: Abre também a porta localhost 8080 (se não passar isso, ele usa apenas o Unix Socket super seguro).
    * `-c, --config <path>`: Aponta para um arquivo de configuração customizado.

* **`herdmaster stop`**
  * **O que faz:** Envia um sinal (SIGTERM) para o processo do HerdMaster que está rodando em background (usando o arquivo PID). É um desligamento seguro (graceful shutdown).

* **`herdmaster status`**
  * **O que faz:** Bate na API de status e retorna uma tabela Rica visualmente com o Uptime, Estado dos agentes, número de tarefas em andamento e os sockets abertos.

* **`herdmaster metrics`**
  * **O que faz:** Retorna todas as métricas internas de performance do orquestrador (formato similar ao Prometheus).

* **`herdmaster agents`**
  * **O que faz:** Lista todos os agentes (janelas do Herdr) conhecidos pelo SQLite, mostrando se estão Saudáveis (*Healthy*), Suspeitos (*Suspect*), e a tarefa atual que cada um está executando.

---

## 2. Comandos de Tarefa (Task Mode)

Estes comandos gerenciam a fila de trabalho direto. Use quando quiser ordenar uma execução pontual.

* **`herdmaster tasks create <TITLE> --prompt <PROMPT>`**
  * **O que faz:** Enfileira uma nova tarefa no banco de dados.
  * **Exemplo:** `herdmaster tasks create "Corrige Bug" --prompt "Edite o arquivo main.py e corrija o erro 404"`
  * **Opções úteis:**
    * `--priority <normal|high|critical>`: Fura a fila se for crítica.
    * `--assigned-to <AGENT_ID>`: Força a tarefa a ser executada apenas na Janela 1 (A1), por exemplo.

* **`herdmaster tasks list`**
  * **O que faz:** Exibe uma tabela com todas as tarefas enfileiradas ou em progresso.
  * **Opções úteis:**
    * `--state <queued|in_progress|done>`: Filtra apenas tarefas pendentes, por exemplo.

* **`herdmaster tasks cancel <TASK_ID>`**
  * **O que faz:** Cancela uma tarefa imediatamente. Se ela estiver rodando num agente, o HerdMaster usará o *Watchdog* para injetar um `Ctrl-C` na janela do agente e abortar o trabalho.

---

## 3. Comandos de Projeto (Project Mode / Tech Lead)

Use esta camada quando quiser que o Agente A1 atue como Arquiteto/Tech Lead e distribua o trabalho por conta própria.

* **`herdmaster projects create <NAME> --scope <SCOPE>`**
  * **O que faz:** Cria o projeto. O HerdMaster envia o *Scope* para o agente orquestrador analisar.
  * **Exemplo:** `herdmaster projects create "Novo Portal" --scope "Faça um front-end em react"`
  * **Opções úteis:**
    * `--orchestrator-id <ID>`: Define qual agente será o Tech Lead (padrão é o A1).

* **`herdmaster projects list`**
  * **O que faz:** Mostra todos os projetos, o status da análise da IA, e o cálculo de ETA (Horas estimadas).

* **`herdmaster projects approve <PROJECT_ID>`**
  * **O que faz:** O humano aprova o plano de quebra de tarefas feito pela Inteligência Artificial.
  * **Opções úteis:**
    * `--decision <accept|modify|override>`: Aceita o plano como está ou substitui a decisão da máquina.

---

## 4. Comandos de Configuração

* **`herdmaster config reload`**
  * **O que faz:** Faz *Hot-Reload*. Bate na API e manda o sistema reler o arquivo `config.toml` (para atualizar regras de segurança/ACL ou verbosidade de Log) sem precisar reiniciar o sistema ou derrubar conexões.

---
*(Nota: Quase todos os comandos suportam a flag `--json` no final, o que faz o CLI retornar os dados crus e limpos para integração com scripts Bash/Python ou interfaces Web).*

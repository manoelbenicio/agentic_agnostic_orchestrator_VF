> **[⚠️ PROTOCOLO MANDATÓRIO]** 
> Todas as features listadas neste Backlog devem ser rigorosamente executadas utilizando o **Framework GSD (Get Shit Done)**. Nenhuma feature pode dar bypass no "Phase Loop" oficial: `Discuss` -> `Plan` -> `Execute` -> `Verify` -> `Ship`. O Tech Lead é o guardião desta regra. Para referência detalhada, consulte a documentação oficial ou o nosso documento interno: `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/docs/GSD_MANDATORY_PROTOCOL.md`.

---

# HerdMaster - Backlog e Próximas Features

Este documento registra os requisitos e solicitações de evolução de produto (Product Roadmap) levantadas nas revisões arquiteturais, priorizadas para logo após a fase de testes e estabilização de qualidade (QA).

---

## [FEATURE-REQ-001] Natural Language Processing (NLP) / ChatOps para o HerdMaster

### Contexto
Atualmente, a comunicação com o Control Plane (HerdMaster) é feita estritamente através da interface de linha de comando (`herdmaster tasks create`, `herdmaster projects create`, etc).
Como o usuário muito bem observou: *"Para nós que somos mais técnicos ok, mas para os usuários certamente a experiência será horrível."*

A imposição de comandos técnicos, flags estritas (`--prompt`, `--assigned-to`) e memorização de sintaxe quebra o fluxo cognitivo e fere a Experiência do Usuário (UX) para times não-técnicos, analistas de negócios ou POs.

### Objetivo
O Agente HerdMaster deve passar a "entender" comandos via Linguagem Natural. Em vez de o usuário atuar como um digitador de terminal, ele atuará como um conversador (Interface Baseada em Intenção - Intent-Based CLI/ChatOps).

### Critérios de Aceite (Proposta)
1. **Nova Interface CLI/Chat:** Implementar um comando simples, como `herdmaster ask "Sua frase aqui"` ou um modo interativo `herdmaster chat`.
2. **LLM Translation Layer:** O HerdMaster receberá o texto em linguagem natural (Ex: *"Crie um projeto para refatorar o login e mande para o agente A1"*) e uma camada interna de IA (LLM/Function Calling) mapeará automaticamente a intenção do usuário para as chamadas da Control API (internamente fazendo o papel de `herdmaster projects create --scope ...`).
3. **Validação Humana:** O sistema de NLP deve ser conversacional. Se o sistema não entender a prioridade, ele pergunta de volta ao usuário antes de enfileirar no SQLite.
4. **Prioridade:** Esta feature tem prioridade máxima no Backlog de Produto, devendo ser iniciada assim que a bateria pesada de testes de stress da infraestrutura atual (Day 1) for concluída e estabilizada.

---

## [FEATURE-REQ-002] Visualização Kanban para Projetos Complexos

### Contexto
Para projetos grandes (com muitas sub-tarefas derivadas pelo Tech Lead), listar todas as tarefas no formato de tabela simples (CLI ou TUI) dificulta a visualização do fluxo de valor (o que está na Fila, o que está Em Progresso, o que está Bloqueado e o que foi Concluído).

### Objetivo
Implementar uma interface de acompanhamento visual baseada em Kanban. Como a arquitetura já possui o conceito de estados bem definidos para as tarefas (`queued`, `assigned`, `in_progress`, `done`, `failed`), o Kanban consumirá nativamente a API do HerdMaster para popular os cards nas colunas corretas em tempo real.

### Critérios de Aceite (Proposta)
1. Pode ser implementado inicialmente como uma nova aba/visão dentro da interface TUI (Terminal UI) para manter os operadores no terminal.
2. Alternativamente, criar um micro-frontend web simples que consome a API HTTP na porta 8080 para exibir o Kanban em um navegador no Day 2.
3. Deve suportar arrastar-e-soltar (drag-and-drop) ou navegação por atalhos de teclado para mudar a prioridade de uma tarefa na fila visualmente.

---

## [FEATURE-REQ-003] Dashboards Avançados e Grafana as Code (Provisionamento Programático)

### Contexto
Atualmente a stack de Observabilidade (Prometheus, Grafana e Blackbox Exporter) está rodando perfeitamente e coletando as métricas, porém não há painéis pré-configurados. Criar gráficos manualmente não é a melhor prática para automação Day 2.

### Objetivo
Desenvolver dashboards altamente sofisticados no Grafana para monitorar a saúde da API (E2E via Blackbox), saúde dos agentes (CPU, tempo de resposta) e o volume do fluxo de trabalho (tarefas pendentes vs concluídas).

### Critérios de Aceite (Proposta)
1. **Abordagem Programática (IaC):** Conforme ótima visão estratégica, a construção **NÃO** será via automação de browser (cliques de agentes em UI), pois isso gera alto custo e lentidão. Faremos tudo de forma programática (*Dashboards as Code*).
2. **Grafana Provisioning:** O agente criará os layouts em arquivos `.json` declarativos e os salvará na pasta `deploy/observability/grafana/dashboards/`.
3. **Plug and Play:** Atualizar o `docker-compose.yml` para ler esses arquivos JSON no boot. Assim, qualquer usuário que subir a stack já terá os dashboards ricos nativamente, com custo zero de operação.

---

## [FEATURE-REQ-004] Desenvolvimento de Solução Proprietária Agnostic-AI (Substituição Estratégica do Multica)

### Contexto
Temos o objetivo de construir uma solução proprietária de inteligência artificial que seja completamente agnóstica em relação aos modelos subjacentes (OpenAI, Anthropic, Google, etc.). Como baseline de inspiração de UI/UX, o sistema "Multica" possui um design excelente (Light/Dark mode) e uma aplicação leve e responsiva. Contudo, a experiência de autenticação do Multica, fortemente dependente de chaves de API (API Keys) inseridas pelo usuário final, gera alta fricção ("experiência lixo") e resulta em custos operacionais desproporcionais e descentralizados.

### Objetivo
Desenvolver nosso próprio produto a partir do zero utilizando tecnologias modernas e as melhores features do mercado. O foco central de inovação será a **reescrita completa do fluxo de autenticação**, substituindo a cobrança/gestão baseada em API Keys por uma autenticação eficiente e econômica utilizando **OAuth por Device Login no Browser** (idêntica à fluidez já consolidada no Herdr e HerdMaster).

### Critérios de Aceite (Proposta)
1. **Ambiente de Benchmarking Integrado:**
   - Realizar o clone do repositório oficial do Multica no GitHub.
   - Subir o ambiente completo do Multica via Docker no nosso ecossistema WSL.
   - Executar o workflow `/opsx-explore` com o ambiente levantado para simular o produto, anotar comportamentos, validar e atualizar a PRD existente, garantindo que não deixamos nenhum requisito funcional/técnico de fora do nosso novo desenvolvimento.
2. **Design e Performance Retidos:** O novo desenvolvimento deve obrigatoriamente manter e evoluir o padrão estético de excelência (Light/Dark mode limpo) e a leveza de processamento observados na concorrência.
3. **Refatoração Crítica de Autenticação:** A solução não deve depender de API Keys no lado do usuário. A autenticação via OAuth/Device Login no browser é **mandatória**, garantindo redução de custos extrema (1000x melhor e mais barato).
4. **Mandatory Observability:** O sistema deve, obrigatoriamente, integrar a stack de Observabilidade Day-2 (Prometheus, Grafana, Dashboards as Code), independente do sizing (tamanho) inicial do projeto.
5. **Manuais de Operação Padronizados:** A entrega exige a geração de Manuais de Operação robustos. Todos os documentos devem referenciar caminhos absolutos nativos do WSL (ex: `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/...`), garantindo compatibilidade perfeita com a infraestrutura agêntica e operacional.

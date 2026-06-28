# Product Requirements Document (PRD)
**Feature:** [FEATURE-REQ-003] Dashboards Avançados e Grafana as Code (Provisionamento Programático)
**Status:** Aprovado para Planejamento / Estimativa de Esforço
**Epic:** Observabilidade Avançada & Day-2 Operations
**Document Owner:** Squad_The_SEALS
**Target Audience:** Tech Lead, C-Level Executives, SREs
**Engineering Framework:** GSD (Get Shit Done) - *[Mandatory compliance: All development phases must follow the GSD phase loop (Discuss, Plan, Execute, Verify, Ship)]*

---

## 1. Executive Summary

### Contexto Atual do Produto (Fase Atual)
O HerdMaster encontra-se na fase de transição de **Estabilização Pós-MVP para Operações Escaláveis (Day-2)**. O núcleo de orquestração (Control Plane), a persistência (SQLite) e a comunicação via socket com o Herdr estão validados e funcionais. A stack de observabilidade base (Prometheus e Blackbox Exporter) está coletando métricas ativamente. No entanto, o Grafana carece de dashboards estruturados, exigindo configuração manual que não escala e não atende aos padrões de automação de uma infraestrutura enterprise.

### Objetivo da Feature
Automatizar o provisionamento de dashboards executivos e operacionais altamente sofisticados no Grafana, utilizando a abordagem **Dashboards as Code (IaC)**. O objetivo é fornecer visibilidade em tempo real sobre a saúde da API, a performance individual dos agentes de IA e o fluxo de tarefas, eliminando intervenções manuais ("ClickOps") e garantindo consistência entre ambientes (DEV → PROD).

---

## 2. Technical Stack & Architecture

### Tech Stack do Produto
*   **Core:** Python 3.12+, Asyncio.
*   **Persistence:** SQLite (`/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/herdmaster.db`).
*   **Observability Base:** Prometheus (Time-series DB), Blackbox Exporter (E2E probing).
*   **Visualization:** Grafana.
*   **Infrastructure:** Docker Compose, WSL (Linux Environment).

### Arquitetura AS-IS (Cenário Atual)
*   O `herdmaster` exporta métricas via endpoint HTTP (`/metrics`).
*   O Prometheus faz o scraping dessas métricas e também invoca o Blackbox Exporter para medir a latência E2E da API (`/status`, `/agents`).
*   O Grafana roda em um container Docker vazio. Não possui datasources predefinidos via código e não possui dashboards. Toda configuração visual depende de ação manual pós-deploy.

### Arquitetura TO-BE (Onde ocorrerão as alterações)
*   **Grafana Provisioning:** Introdução de arquivos de configuração declarativa mapeados como volumes no container do Grafana.
    *   `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability/grafana/datasources/datasource.yml`: Aponta automaticamente para o Prometheus local.
    *   `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability/grafana/dashboards/dashboards.yml`: Instrui o Grafana a carregar JSONs de um diretório específico.
    *   `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability/grafana/dashboards/herdmaster_main.json`: O dashboard principal, codificado em JSON, seguindo rigorosamente o **Fortune 500 Executive Dashboard Design System**.

---

## 3. Design System & Visual Guidelines

A implementação do JSON do dashboard (`herdmaster_main.json`) **DEVE** aderir mandatoriamente aos padrões do `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/data_expert_skills/fortune500-executive-dashboard.md` (Catálogo de Super Skills):
*   **Tema:** Dark Mode (`--bg-primary: #080b10`).
*   **Paleta Semântica:** Verde (`#36d399`) para saúde, Vermelho (`#ff5c7a`) para falhas.
*   **Hierarquia de Informação ("5-Second Scan"):**
    1.  **Level 1 (Hero KPIs):** Top row com Total Agents, Healthy, Active Projects, API Status.
    2.  **Level 2 (Per-Agent Breakdown):** Tabela de status ao vivo com color-coding por role e saúde. Gauge bars para Health Score.
    3.  **Level 3 (Task Queue & Performance):** Gráficos de séries temporais (stacked) para tarefas por estado e duração média.

---

## 4. Execution Plan (Fases do Ciclo de Vida)

### Phase 1: Desenvolvimento (DEV)
1.  **Datasource as Code:** Criar `datasource.yml` apontando para `http://localhost:9090` (Prometheus) com autenticação base se necessário.
2.  **Dashboard Provisioning:** Criar `dashboards.yml` para mapear a pasta `/etc/grafana/provisioning/dashboards`.
3.  **JSON Construction:** Construir o `herdmaster_main.json` programaticamente, utilizando as queries PromQL já validadas (ex: `herdmaster_agents_total`, `probe_success`).
4.  **Integração Docker:** Atualizar o `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability/docker-compose.yml` para montar os diretórios `datasources` e `dashboards` nativamente no container do Grafana.

### Phase 2: Quality Assurance (QA)
1.  **Validation:** Subir a stack localmente (`docker compose up -d`).
2.  **Verification:** Acessar o Grafana (porta 3000) e verificar se o dashboard é carregado automaticamente sem necessidade de login prévio de admin para setup.
3.  **Data Flow Test:** Rodar scripts do HerdMaster para simular carga e garantir que os gráficos de Gauge, Timeseries e Tabelas respondem corretamente e respeitam a paleta de cores (ex: alertas vermelhos quando um agente cai).
4.  **Design System Audit:** Validar se a UI obedece à hierarquia "Executive Density".

### Phase 3: Estratégia de Deploy (DEV -> PROD)
*   **Risco Mínimo (Zero Downtime):** O deploy consiste apenas na atualização dos arquivos `.yml` e `.json` na pasta `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability/grafana/`.
*   **Estratégia:** 
    1. Git commit e merge na branch `main`.
    2. No servidor de PROD, executar `git pull`.
    3. Rodar `docker compose restart grafana`. O Grafana recarregará os artefatos provisionados sem afetar a coleta de métricas do Prometheus ou o Control Plane do HerdMaster. Impacto sistêmico nulo.

### Phase 4: Plano de Testes com Usuário (UAT)
*   **Sessão de Apresentação C-Level:** O dashboard será apresentado em modo tela cheia.
*   **Teste do "Boardroom Test" (5-Second Scan):** Medir o tempo que o Stakeholder leva para identificar: 1) A saúde geral do sistema; 2) Qual agente está ocioso vs trabalhando; 3) A latência atual da API.
*   **Feedback Loop:** Ajustar queries PromQL e limites de Gauge (Thresholds) com base na percepção de valor de negócios.

---

## 5. Prós e Contras (Análise de Risco)

| Fator | Avaliação | Impacto |
| :--- | :--- | :--- |
| **PRO: Escalabilidade** | Deploy padronizado. Qualquer nova instância do HerdMaster já nasce com observabilidade C-level configurada. | Alto (Positivo) |
| **PRO: GitOps/IaC** | O dashboard entra em versionamento de código. Alterações ficam registradas no histórico do Git, permitindo rollbacks instantâneos. | Alto (Positivo) |
| **PRO: Experiência Premium** | Demonstra maturidade técnica para clientes Enterprise (Fortune 500). | Alto (Positivo) |
| **CON: Curva de Manutenção** | Atualizar dashboards complexos alterando JSON diretamente requer alto conhecimento estrutural do esquema do Grafana. | Baixo (Mitigado por automação e versionamento) |

---

## 6. Parecer Técnico (Agentic Skills Review)
A construção e evolução deste dashboard utilizará perfis avançados de orquestração multi-agente (`multi-agent-architect`, `agent-evaluation`, `agentic-actions-auditor`). Estes skills garantem que o dashboard não apenas mostre "Infraestrutura" (CPU/RAM), mas sim **KPIs Agênticos** (Agent Confidence Score, Task Loop Count, Auditoria de Chain of Thought), elevando o produto a uma plataforma madura de IA Orquestrada. A referência completa encontra-se em `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/docs/super_skills_agentic_catalog.md` e a base de conhecimento estruturada em `/mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/docs/all_skills_by_group`.

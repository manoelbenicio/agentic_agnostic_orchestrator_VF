# AOP — Documentação de Deploy, Operação e Governança

> **AOP (Agnostic Orchestration Platform)** — plataforma SaaS multi-tenant para orquestração de squads de agentes de IA (Codex, Kiro, Gemini, GLM, etc.), com execução dual-mode (terminal/multiplexador via Herdr + socket/HTTP via HerdMaster), FinOps granular em tempo real e observabilidade Prometheus/Grafana.

Esta documentação foi **reconstruída do zero** (pt-BR). Todo o material legado foi arquivado em [`../OLD/`](../OLD/) e **não deve ser reutilizado**. Cada afirmação técnica aqui é verificada contra os arquivos-fonte reais do repositório; comandos de verificação de runtime são fornecidos para a squad executar — **nenhuma saída de serviço foi fabricada**.

---

## Princípios desta documentação

1. **Fonte única da verdade.** Zero duplicação, zero contradição entre arquivos.
2. **Toda afirmação cita arquivo/comando real** + bloco de verificação reproduzível.
3. **Status honesto.** Só marcamos "pronto" o que tem evidência reproduzível. Lacunas (gaps) são declaradas explicitamente.
4. **Fatos extraídos do legado, estrutura descartada.** O `OLD/` serve só como fonte de fatos.

---

## Índice mestre

### 00 — Visão & Arquitetura
- [`00-VISAO-ARQUITETURA.md`](00-VISAO-ARQUITETURA.md) — visão de produto, topologia de serviços, mapa de portas, estado real x pretendido.

### 10 — Deploy
- [`10-DEPLOY/11-PRE-REQUISITOS.md`](10-DEPLOY/11-PRE-REQUISITOS.md) — binários, versões, layout de diretórios irmãos (AOP + HerdMaster).
- [`10-DEPLOY/12-INSTALACAO.md`](10-DEPLOY/12-INSTALACAO.md) — preparação de venv, dependências, primeira subida.
- [`10-DEPLOY/13-VARIAVEIS-AMBIENTE.md`](10-DEPLOY/13-VARIAVEIS-AMBIENTE.md) — `.env`, variáveis derivadas, `DATABASE_URL`/`REDIS_URL`.
- [`10-DEPLOY/14-SEGREDOS-E-TOKENS.md`](10-DEPLOY/14-SEGREDOS-E-TOKENS.md) — token HerdMaster, cópia para Prometheus, permissões.
- [`10-DEPLOY/15-COMPOSE-E-SERVICOS.md`](10-DEPLOY/15-COMPOSE-E-SERVICOS.md) — `docker-compose.yml`, rede, volume, healthchecks.

### 20 — Operação
- [`20-OPERACAO/21-SUBIR-E-DERRUBAR.md`](20-OPERACAO/21-SUBIR-E-DERRUBAR.md) — `start.sh` / `stop.sh`, ordem de boot, idempotência.
- [`20-OPERACAO/22-BACKUP-RESTORE.md`](20-OPERACAO/22-BACKUP-RESTORE.md) — `db-backup.sh` / `db-restore.sh`, retenção, cron.
- [`20-OPERACAO/23-OBSERVABILIDADE.md`](20-OPERACAO/23-OBSERVABILIDADE.md) — Prometheus/Grafana/Alertmanager/Blackbox/Remediação.
- [`20-OPERACAO/24-RUNBOOK-INCIDENTES.md`](20-OPERACAO/24-RUNBOOK-INCIDENTES.md) — diagnóstico e recuperação por componente.
- [`20-OPERACAO/25-STATUS360-E-DASHBOARD.md`](20-OPERACAO/25-STATUS360-E-DASHBOARD.md) — `status360.py`, `flush-restart.sh`.

### 30 — Componentes
- [`30-COMPONENTES/31-CONTROL-PLANE.md`](30-COMPONENTES/31-CONTROL-PLANE.md) — FastAPI, endpoints, routers.
- [`30-COMPONENTES/32-WEB-FRONTEND.md`](30-COMPONENTES/32-WEB-FRONTEND.md) — Next.js, rotas, Indra DSS v3.0.
- [`30-COMPONENTES/33-COUPLING-HERDMASTER-HERDR.md`](30-COMPONENTES/33-COUPLING-HERDMASTER-HERDR.md) — acoplamento e degradação graciosa.
- [`30-COMPONENTES/34-EXECUCAO-DUAL-MODE.md`](30-COMPONENTES/34-EXECUCAO-DUAL-MODE.md) — executores terminal/socket (estado real, stubs).
- [`30-COMPONENTES/35-FINOPS-E-CUSTOS.md`](30-COMPONENTES/35-FINOPS-E-CUSTOS.md) — engine de custos, gaps e roadmap premium.
- [`30-COMPONENTES/36-ROTACAO-CONTAS-TOKEN.md`](30-COMPONENTES/36-ROTACAO-CONTAS-TOKEN.md) — rotação automática de contas ao esgotar tokens (janela 5h).

### 40 — Verificação
- [`40-VERIFICACAO/41-SMOKE-E2E.md`](40-VERIFICACAO/41-SMOKE-E2E.md) — `e2e/smoke_e2e.py`, discrepâncias conhecidas.
- [`40-VERIFICACAO/42-CHECKLIST-TEST-READY.md`](40-VERIFICACAO/42-CHECKLIST-TEST-READY.md) — gate "pronto para testar com agentes reais".
- [`40-VERIFICACAO/43-TESTE-DE-CARGA.md`](40-VERIFICACAO/43-TESTE-DE-CARGA.md) — plano de carga/concorrência.

### 50 — Governança da Squad
- [`50-GOVERNANCA-SQUAD/51-COMPOSICAO-SQUAD.md`](50-GOVERNANCA-SQUAD/51-COMPOSICAO-SQUAD.md) — 8 agentes, papéis, modelos.
- [`50-GOVERNANCA-SQUAD/52-PARALELISMO-E-ONDAS.md`](50-GOVERNANCA-SQUAD/52-PARALELISMO-E-ONDAS.md) — ondas, isolamento, anticolisão.
- [`50-GOVERNANCA-SQUAD/53-PROTOCOLO-CHECKIN-OUT.md`](50-GOVERNANCA-SQUAD/53-PROTOCOLO-CHECKIN-OUT.md) — ledger obrigatório em disco.
- [`50-GOVERNANCA-SQUAD/54-COORDENACAO-TECH-LEAD.md`](50-GOVERNANCA-SQUAD/54-COORDENACAO-TECH-LEAD.md) — papel do Opus 4.8 coordenador.

### 90 — Decisões
- [`90-DECISOES/91-ADRs.md`](90-DECISOES/91-ADRs.md) — decisões arquiteturais (irreversíveis e em aberto).
- [`90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md`](90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md) — pesquisa de mercado FinOps/observabilidade nível Fortune 500.

---

## Ordem de leitura recomendada para a squad

1. `00-VISAO-ARQUITETURA.md` (contexto)
2. Bloco `10-DEPLOY` inteiro (instalar)
3. Bloco `20-OPERACAO` (operar)
4. `40-VERIFICACAO/42-CHECKLIST-TEST-READY.md` (gate de prontidão)
5. Bloco `50-GOVERNANCA-SQUAD` (antes de qualquer agente tocar código)

> **Escopo desta entrega:** apenas planejamento/documentação. **Não** executa o deploy real (sem `docker up`, sem serviços rodando). A squad agêntica executa o deploy depois, seguindo estes documentos.

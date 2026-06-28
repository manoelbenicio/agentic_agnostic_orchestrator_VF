# MANDATORY PROTOCOL: GSD (Get Shit Done) Framework

**Status:** ATIVO E OBRIGATÓRIO PARA TODOS OS PROJETOS E SQUADS
**Aplicabilidade:** Todas as features, do levantamento ao deploy.

---

## 1. Diretriz Executiva
Por determinação da liderança, **TODOS os projetos** (incluindo o `FEATURE-REQ-003` e o `FEATURE-REQ-004`) devem ser estritamente executados seguindo o framework **GSD Core (@opengsd/gsd-core)**. 

É expressamente proibido dar "bypass" em qualquer etapa do ciclo de vida. O Tech Lead é o responsável direto por garantir a conformidade com as fases abaixo.

## 2. O Ciclo Obrigatório (The Phase Loop)
Nenhum código será mesclado ou implantado sem que as seguintes fases existam formalmente na pasta `.planning/` do projeto:

1. **Discuss Phase (`/gsd-discuss-phase`):** Captura de decisões de design, entrevistas de requisitos e validação arquitetural antes de qualquer planejamento.
2. **Plan Phase (`/gsd-plan-phase`):** Pesquisa, decomposição do trabalho (Task Breakdown) e verificação da qualidade do plano gerado.
3. **Execute Phase (`/gsd-execute-phase`):** Execução do plano através de agentes paralelos (sub-agentes com contexto isolado).
4. **Verify & Ship (`/gsd-verify` / `/gsd-ship`):** Diagnóstico de falhas, validação de edge cases, testes de QA e criação estruturada do Pull Request.

## 3. Instalação e Ambiente (Antigravity & WSL)
Como o ecossistema roda de forma agêntica, a instalação do núcleo do GSD deve estar presente no runtime local. 
Para ambientes baseados no **Antigravity** (nossa stack atual), o Tech Lead deve assegurar que o core está instalado:

```bash
# Executar no ambiente WSL/Node.js nativo (Node 18+)
npx @opengsd/gsd-core@latest --antigravity --global
```

*Nota para Operações Windows:* Caso haja execução direta no Windows, utilizar WSL, VMs ou os scripts nativos fornecidos pela documentação oficial (Option A/Option B).

## 4. Governança e Observabilidade
A metodologia GSD impõe o monitoramento de contexto (Context Headroom) e auditoria contínua de ações agênticas (Hooks). A integração desses hooks de segurança e limites de memória (Agent Memory) deve andar lado a lado com os dashboards do Prometheus/Grafana descritos na PRD. Todos os manuais do projeto devem prever que a orquestração ocorre via GSD.

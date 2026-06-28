# 92 — Pesquisa de Ferramentas Premium (FinOps, Observabilidade, Billing)

> Pesquisa de mercado (2025–2026) para elevar a AOP a **nível Fortune 500 / premium** em FinOps de IA, observabilidade de agentes e billing por uso. Cada recomendação é mapeada contra as **lacunas reais** da AOP (docs 34 e 35). Conteúdo foi parafraseado para conformidade com licenciamento; fontes citadas inline.

---

## 1. Por que isto importa para a AOP

As lacunas verificadas (doc 35): FinOps não é alimentado automaticamente, custo só por tenant/projeto, `model` apenas em metadata, exporter Prometheus fixo. O mercado já consolidou padrões e ferramentas open-source que resolvem exatamente esses problemas. Adotá-los encurta o caminho e dá credibilidade enterprise.

Tema recorrente em 2026: a métrica relevante deixou de ser "custo por token" e passou a ser **custo por resultado/atribuição** — cada chamada de LLM gera traces, contagem de tokens, latência e custo que precisam ser atribuídos a usuário/time/feature. Fontes: [implicator.ai — LLM token monitoring 2026](https://www.implicator.ai/the-best-llm-token-monitoring-tools-in-2026-and-which-one-you-actually-need-2/), [futureagi.com — LLM spend tracking 2026](https://futureagi.com/blog/llm-spend-cost-tracking-2026/). *Conteúdo reformulado para conformidade.*

---

## 2. Padrões a adotar (fundação, antes de ferramentas)

### 2.1 OpenTelemetry GenAI Semantic Conventions
Padrão aberto que define atributos `gen_ai.*` para instrumentar chamadas de LLM, execuções de ferramentas e operações de agentes — modelo, contagem de tokens de entrada/saída, motivo de término — coletáveis por um OTel Collector e consultáveis no Grafana/Tempo. Fontes: [OpenTelemetry — GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans), [OpenTelemetry — GenAI observability (blog 2026)](https://opentelemetry.io/blog/2026/genai-observability/), [uptrace.dev — OTel for AI systems](https://uptrace.dev/blog/opentelemetry-ai-systems).

**Aplicação na AOP:** padronizar os eventos de `tracing` e o `metadata` do FinOps usando os nomes `gen_ai.*` (modelo, tokens in/out, vendor). Isso torna a telemetria interoperável com qualquer backend OTel e alimenta o breakdown por modelo que falta hoje. → resolve doc 35 §4 (por modelo) e doc 23 §2 (exporter).

### 2.2 FOCUS — FinOps Open Cost and Usage Specification
Especificação aberta da FinOps Foundation que **normaliza dados de billing** entre nuvem, SaaS, data center e **IA**, mapeando atributos de consumo para colunas padronizadas (ex.: quantidade consumida, unidade, custo efetivo, ID de recurso). Fontes: [focus.finops.org](https://focus.finops.org/), [focus.finops.org — What is FOCUS](https://focus.finops.org/what-is-focus/), [Microsoft — Learning FOCUS](https://techcommunity.microsoft.com/blog/finopsblog/learning-focus-introducing-an-open-billing-data-format/4321609).

**Aplicação na AOP:** mapear os `CostRecord`/rollups para o esquema FOCUS (colunas como `BilledCost`, `ConsumedQuantity`, `ConsumedUnit`, `ResourceId`, `ServiceName`). Dá ao cliente Fortune 500 dados de custo no formato que as equipes FinOps dele já entendem. → eleva doc 35 a padrão de indústria.

---

## 3. Gateway de LLM (resolve alimentação automática + budgets)

### LiteLLM Proxy (AI Gateway) — **recomendação forte**
Proxy/gateway que expõe 100+ LLMs numa interface unificada estilo OpenAI e **rastreia spend e impõe budgets por virtual key / usuário / time**, com tags de custo, mapeamento JWT→virtual key, alertas/webhooks e relatórios de gasto. O custo é calculado automaticamente para modelos conhecidos (model cost map). Multi-tenancy via Teams (open source) e Organizations (enterprise). Fontes: [docs.litellm.ai — Proxy](https://docs.litellm.ai/docs/simple_proxy), [LiteLLM — Spend Tracking](https://docs.litellm.ai/docs/proxy/cost_tracking), [LiteLLM — Multi-Tenant Architecture](https://docs.litellm.ai/docs/proxy/multi_tenant_architecture), [LiteLLM — Team Budgets](https://docs.litellm.ai/docs/proxy/team_budgets), [LiteLLM — Tag Budgets](https://docs.litellm.ai/docs/proxy/tag_budgets).

**Aplicação na AOP:** rotear as chamadas de LLM dos agentes através do LiteLLM. Cada agente/tenant/projeto vira uma virtual key ou tag → spend e budget **automáticos e por modelo**, sem o caller informar preço. A AOP consome os spend logs do LiteLLM e os reflete no seu FinOps. → resolve diretamente o **bloqueador nº1** (doc 34 §4) e a granularidade por modelo (doc 35).

> Trade-off (OPEN-1, doc 91): adotar LiteLLM (menos código, padrão de mercado, budgets prontos) vs instrumentar diretamente cada SDK de vendor. Recomendação: LiteLLM como camada de custo + OTel para tracing.

---

## 4. Observabilidade de LLM/agentes (traces + custo por span)

Opções open-source maduras (todas alinhadas a OTel em algum grau):

| Ferramenta | Foco | Nota |
|-----------|------|------|
| **Langfuse** | tracing, custo por trace, evals, self-host | forte em atribuição por trace/usuário |
| **OpenLLMetry (Traceloop)** | instrumentação OTel-nativa para libs de LLM | [github.com/traceloop/openllmetry](https://github.com/traceloop/openllmetry) |
| **Arize Phoenix** | observabilidade/evals open-source | bom para qualidade de output |
| **Helicone** | proxy + custo/uso | rápido de plugar |

Fontes comparativas: [posthog.com — cheapest AI observability tools](https://posthog.com/blog/cheapest-ai-observability-tools), [amnic.com — AI token management tools 2026](https://amnic.com/blogs/ai-token-management-tools), [futureagi.com — best LLM cost tracking 2026](https://futureagi.com/blog/best-llm-cost-tracking-tools-2026/). *Comparações reformuladas para conformidade.*

**Aplicação na AOP:** **OpenLLMetry/Traceloop** encaixa melhor porque é OTel-nativo — alimenta o mesmo pipeline Prometheus/Grafana já presente (doc 23) e os atributos `gen_ai.*` (§2.1). **Langfuse** é alternativa se quisermos um backend de tracing/eval dedicado com UI própria.

### tokencost — utilitário leve de preço
Biblioteca Python que estima custo em USD de prompts/completions para 400+ LLMs (TokenOps). Fonte: [github.com/AgentOps-AI/tokencost](https://github.com/AgentOps-AI/tokencost).

**Aplicação na AOP:** alimentar o **catálogo de preços por modelo** (doc 35 §5 item 5) sem manter tabela de preços à mão, caso não se use o model cost map do LiteLLM.

---

## 5. Billing por uso / assinatura (fase 2/3, mas decidir cedo)

Quando entrarem os módulos de aluguel/assinatura (ADR-005), o mercado open-source oferece:

| Ferramenta | O que é | Fonte |
|-----------|---------|-------|
| **Lago** | metering + usage-based & subscription billing, self-host, event-based realtime | [github.com/getlago/lago](https://github.com/getlago/lago), [getlago.com/docs/guide](https://getlago.com/docs/guide) |
| **OpenMeter** | metering de uso em tempo real para casos de IA/DevOps + billing | [openmeter.io](https://openmeter.io/llms.txt), [github.com/openmeterio](https://github.com/SpeechifyInc/openmeter) |

**Aplicação na AOP:** os eventos de custo/uso da AOP (token e seat) são exatamente os "usage events" que Lago/OpenMeter consomem para gerar fatura. Modelar o FinOps agora (FOCUS + OTel) facilita plugar billing depois sem retrabalho. → prepara fase 2/3 sem bloquear a fase atual.

---

## 6. Arquitetura-alvo recomendada (premium)

```
Agentes (Codex/Gemini/GLM/Kiro)
   │  chamadas LLM
   ▼
LiteLLM Proxy  ──spend logs/budgets──►  AOP FinOps (CostRecord + FOCUS mapping)
   │  (OTel gen_ai.* spans)                     │
   ▼                                            ▼
OTel Collector ──► Prometheus ──► Grafana (breakdown realtime: tenant/projeto/modelo/task/agente/Kanban)
                                   │
                                   └──► Alertmanager (orçamentos estourados)
   (fase 2/3) AOP usage events ──► Lago/OpenMeter ──► fatura do cliente
```

### Mapa lacuna → solução

| Lacuna (doc 34/35) | Solução premium |
|--------------------|-----------------|
| FinOps não alimentado automaticamente | LiteLLM gateway (spend automático) + gancho no dispatch |
| Custo só por tenant/projeto | tags/keys do LiteLLM + agregações novas + esquema FOCUS |
| `model` só em metadata | atributos `gen_ai.*` (OTel) + rollup por modelo |
| Exporter Prometheus fixo | métricas OTel rotuladas (tenant/project/model/vendor) |
| Sem catálogo de preços | LiteLLM model cost map **ou** tokencost |
| Sem orçamentos/alertas | budgets do LiteLLM + Alertmanager |
| Billing (fase 2/3) | Lago ou OpenMeter consumindo usage events |

---

## 7. Recomendação de priorização (para o TL)

1. **Adotar padrões primeiro** (baixo custo, alto retorno): OTel GenAI semconv + mapear rollups para FOCUS.
2. **Introduzir LiteLLM** como gateway de custo/budget → fecha o bloqueador de FinOps automático.
3. **OpenLLMetry** para tracing OTel-nativo no pipeline Prometheus/Grafana existente.
4. **tokencost / model cost map** para preços por modelo.
5. **Lago/OpenMeter** quando a fase 2/3 (billing) começar.

> Todas as ferramentas citadas são open-source/self-hostable, compatíveis com o bind `127.0.0.1` e o desenho atual (Postgres/Redis/Prometheus/Grafana). Nenhuma exige enviar código ou segredos da AOP para terceiros — alinhado a um produto Fortune 500.

---

### Fontes (resumo)
- FinOps FOCUS: focus.finops.org; Microsoft FinOps blog.
- OpenTelemetry GenAI: opentelemetry.io (spans, metrics, blog 2026); uptrace.dev.
- LiteLLM: docs.litellm.ai (proxy, cost_tracking, multi_tenant, budgets, tags).
- Observabilidade: traceloop/openllmetry (GitHub), posthog.com, amnic.com, futureagi.com.
- tokencost: AgentOps-AI/tokencost (GitHub).
- Billing: getlago/lago (GitHub), openmeter.io.

> *Conteúdo desta página foi parafraseado/resumido a partir das fontes citadas para conformidade com restrições de licenciamento; nenhuma reprodução literal extensa foi feita.*

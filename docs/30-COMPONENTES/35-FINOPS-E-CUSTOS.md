# 35 — FinOps e Custos

Origem da verdade: `control-plane/finops/engine.py`, `finops/models.py`, `finops/repository.py`, e os endpoints em `app/main.py`.

## 1. Modelo de custo (dual engine)

A AOP calcula custo por **dois motores** (`CostEngine`):

### TOKEN (pay-as-you-go) — `record_token_usage`
```python
cost = input_tokens * input_token_price_usd + output_tokens * output_token_price_usd
```
Persiste `CostRecord` com `usage_units = {input_tokens, output_tokens, total_tokens}` e `metadata = {"model": <modelo>, ...}`.

### SEAT (assinatura) — `record_seat_usage`
```python
share = used_seconds / period_seconds          # exige period_seconds > 0
cost  = period_cost_usd * share
```
Persiste o `CostRecord` **e** uma observação em `finops_seat_usage` (para right-sizing de seats ociosos).

A `Attribution` (cadeia hierárquica) é: `tenant_id → project_id → issue_id → agent_id → runtime_id`.

---

## 2. Persistência (`finops/repository.py`)

- Tabela `finops_cost_records` (custo por registro) — colunas: engine, billing_mode, tenant/project/issue/agent/runtime, trace_id, cost_usd, usage_units (JSONB), metadata (JSONB), occurred_at.
- Tabela `finops_seat_usage` (observações de utilização de seat).
- **Rollup de projeto** (`rollup_project`): soma `total`, `token_total`, `seat_total` e `count`, agrupando por `tenant_id + project_id`.
- **Right-sizing** (`idle_seat_recommendations`): utilização por seat; marca `idle` abaixo de `idle_threshold_pct` (default 10%).

---

## 3. Endpoints FinOps

| Método | Rota | Observação |
|--------|------|------------|
| POST | `/finops/costs/token` | recebe tokens + preços + `model` + `trace_id` |
| POST | `/finops/costs/seat` | recebe seat_id, vendor, used/period seconds, period_cost |
| GET | `/finops/projects/{tenant}/{project}/rollup` | total, token_cost, seat_cost, record_count |

---

## 4. ⚠️ Lacunas verificadas x visão de produto

A **visão** pede breakdown realtime por: projeto, **task**, **grupo de TLs**, **grupo de agentes**, **Kanban** e **por modelo** (OpenAI/Gemini/...). O **estado real** é:

| Dimensão pedida | Estado no código | Lacuna |
|-----------------|------------------|--------|
| Por projeto | ✅ `rollup_project` | ok |
| Token vs Seat | ✅ separado no rollup | ok |
| Por **modelo** | ⚠️ `model` só em `metadata` (JSONB); **não** há rollup por modelo | precisa de agregação por `metadata->>'model'` |
| Por **task/issue** | ⚠️ `issue_id` é persistido, mas não há endpoint de rollup por issue | precisa endpoint |
| Por **agente/grupo de agentes** | ⚠️ `agent_id` persistido; sem rollup por agente/grupo | precisa endpoint + conceito de "grupo" |
| Por **grupo de TLs** | ❌ não há conceito de "grupo de TL" no schema | precisa modelar |
| Por **Kanban** | ❌ não há vínculo custo↔Kanban/coluna | precisa modelar |
| **Realtime** | ⚠️ `/metrics` expõe FinOps só para `tenant-a`/`project-a` **fixos** | exporter precisa ser multi-tenant/dinâmico |
| **Alimentação automática** | ❌ executores não chamam o engine (ver doc 34) | **bloqueador** para teste com agente real |

> Resumo honesto: a **base** de custo dual (token+seat) e a persistência hierárquica existem e funcionam (provado no smoke E2E, doc 41). O que falta para o nível "premium/Fortune 500" é (a) **alimentação automática** pelos executores, (b) **agregações multidimensionais** (modelo/task/agente/grupo/Kanban) e (c) **exporter Prometheus dinâmico**.

---

## 5. Roadmap para "FinOps pronto para agentes reais"

Ordem sugerida (detalhe técnico e ferramentas em [`90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md`](../90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md)):

1. **Adaptadores nativos por vendor** (doc 34 §5) que extraiam tokens/modelo reais e chamem `record_token_usage` ao fim de cada turno do agente.
2. **Gancho automático no dispatch** dos executores: ao detectar uso, gravar custo com a `Attribution` correta + `trace_id` (correlaciona com tracing).
3. **Agregações novas no repository**: `rollup_by_model`, `rollup_by_issue`, `rollup_by_agent`, e modelagem de "grupo de TL/agente" e vínculo Kanban (coluna/board id na `Attribution` ou em `metadata`).
4. **Exporter Prometheus dinâmico**: substituir o par fixo `tenant-a/project-a` por métricas rotuladas (`tenant`, `project`, `model`, `vendor`) para Grafana fazer o breakdown realtime.
5. **Catálogo de preços por modelo**: tabela de preços (input/output por 1k tokens) por modelo/vendor, versionada — base para custo correto sem o caller informar preço a cada POST.
6. **Orçamentos e alertas**: limites por tenant/projeto/grupo, com alerta via Alertmanager ao ultrapassar.

---

## 6. Verificação (estado atual)

```bash
# Registrar custo de token manualmente e ver o rollup subir:
curl -s -X POST http://127.0.0.1:8090/finops/costs/token -H 'Content-Type: application/json' -d '{
  "tenant_id":"t1","project_id":"p1","issue_id":"i1","agent_id":"a1","runtime_id":"a1",
  "input_tokens":1000,"output_tokens":500,
  "input_token_price_usd":"0.000003","output_token_price_usd":"0.000015",
  "model":"gpt-x","trace_id":"tr1"}' | python3 -m json.tool

curl -s http://127.0.0.1:8090/finops/projects/t1/p1/rollup | python3 -m json.tool
# total_cost_usd > 0, record_count >= 1

# Confirmar que o breakdown por modelo NÃO existe via API hoje (só metadata):
echo "Não há GET /finops/.../rollup?by=model — lacuna documentada acima."
```

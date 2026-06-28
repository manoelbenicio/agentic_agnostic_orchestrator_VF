# SPEC — FASE 5 · FinOps + Observability + Live (KPIs premium + efeitos)
**Dono:** AG-5 · **Status:** ready (APIs existem) · **Depende de:** F0

## Discuss
APIs de finops/tracing/health existem; faltam telas premium com componentes de KPI e efeitos.

## WHAT
- FinOps: motor token×seat, rollup por projeto, detecção de seat ocioso; KPI cards/gauges/progress
  (princípios `visual-kpi-designer`, sem código pptx); filtros (tenant/projeto/período); export CSV; tom executivo (headline = conclusão).
- Observability: cards de saúde (coupling/postgres/redis), alertas (Alertmanager), links Grafana, gráfico quota/burn.
- Live: trace por agente E por runtime (WS + fallback), burn individual, filtros por tipo.

## Escopo de paths
`AOP/web/src/app/{finops,observability,live}/**`, `components/{finops,observability,live}/**`. Lê APIs read-only.

## Aceite (UAT)
- [ ] Dados reais (sem mock); rollup por projeto; token vs seat; quota/burn.
- [ ] Micro-animações sutis nos KPIs; tom executivo.
- [ ] build verde. **Print** em `AOP/.planning/evidence/AG-5-finops.png`.

## Evidência obrigatória
build + curls finops/tracing/health + PRINT real no ledger raiz.

# SPEC — FASE 7 · E2E + UI Review (6 pilares) + Perf/A11y
**Dono:** rotativo (designado pelo TL) · **Status:** blocked-by F0..F6

## WHAT
- Smoke E2E completo ponta-a-ponta: criar squad no canvas → topologia vira ACL → dispatch terminal/socket
  → trace por agente/runtime → custo no FinOps → bloqueio lateral default-deny comprovado.
- `gsd-ui-review` (6 pilares): hierarquia visual, espaçamento/alinhamento, cor/contraste (tokens Indra HEX),
  tipografia, consistência de componentes, micro-interações.
- Performance (Lighthouse) + acessibilidade (foco/contraste/teclado).

## Escopo de paths
`AOP/e2e/**`, `AOP/.planning/ui-review/**`. Lê tudo read-only.

## Aceite (UAT)
- [ ] E2E `overall: passed` (relatório); UI-review sem itens críticos; sem regressão de build.
- [ ] **Print** do app final + relatório em `AOP/.planning/evidence/F7-e2e-uireview/`.

## Evidência obrigatória
relatório E2E + UI-review + PRINTs no ledger raiz.

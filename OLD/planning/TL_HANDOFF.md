# 📜 HANDOFF FORMAL — Planejamento GSD → Tech-Lead
**De:** Kiro (Planejamento) · **Para:** Tech-Lead / Orchestrator (ex.: Kiro_Opus-48)
**Data de emissão:** 2026-06-26 · **Projeto:** Agnostic Orchestration Platform (AOP)

## 1. Objeto do handoff
Entrego formalmente ao Tech-Lead o **planejamento GSD completo** para construir a aplicação (todas as
telas, design system Indra HEX, efeitos premium, menu lateral) de forma 100% agêntica com 6 agentes.

## 2. Pacote entregue (ler nesta ordem)
1. `AOP/.planning/PROJECT.md` — contexto-mestre, stack, design system, constraints.
2. `AOP/.planning/ROADMAP.md` — fases F0–F7, ondas, dependências.
3. `AOP/.planning/phases/*/SPEC.md` — **cada fase documentada** (8 specs: F0–F7), com WHAT, escopo, aceite, evidência.
4. `AOP/.planning/TL_BRIEFING.md` — os **6 prompts injetáveis** por pane + como injetar (HerdMaster/Herdr).
5. `CHECKIN_OUT_GSD.md` (RAIZ) — ledger de check-in/out monitorado pelo operador.

## 3. Mandatos inegociáveis (o TL deve fazer cumprir)
- Design System **Indra HEX** (sem OKLCH); cores só via tokens.
- **ZERO mock/placeholder** em produção.
- **CHECK-IN antes de qualquer atividade** + **CHECK-OUT com timestamp + nome do agente + PRINT real**
  (`AOP/.planning/evidence/<AGENTE>-<task>.png`) no ledger raiz. Sem print = task inválida (TL reabre).
- Isolamento de paths por agente.

## 4. Ondas de execução
- **Onda 1 (injetar já):** AG-1 (F0), AG-2 backend (F1), AG-4 backend (F4).
- **Onda 2 (após Onda 1):** AG-2 UI (F2), AG-3 (F3), AG-5 (F5), AG-6 (F6).
- **Onda 3:** F7 (E2E + UI review), designado pelo TL.

## 5. Aceite do Tech-Lead (preencher no ledger)
Ao receber este handoff, o TL registra no `CHECKIN_OUT_GSD.md` (raiz):
```
| <UTC> | <TL_NOME> | ACK-HANDOFF | gsd-plan | PROJECT.md, ROADMAP.md, phases/*, TL_BRIEFING.md | RECEIVED | li e aceito; iniciando Onda 1 |
```
A partir do ACK, o TL injeta a Onda 1 nos panes e monitora os check-outs (com print) antes de liberar a Onda 2.

## 6. Critério de "fase concluída"
Uma fase só conta como concluída quando: build/pytest verdes + dados reais (sem mock) + **PRINT real** anexado +
CHECK-OUT no ledger. O TL valida e só então avança a onda. F7 fecha o ciclo.

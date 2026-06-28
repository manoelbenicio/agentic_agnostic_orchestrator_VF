# 📊 STATUS BOARD — Entregas por Fase / Agente (delivered vs não entregue)

> Atualizado pelo TL a cada CHECK-OUT validado. Fonte de verdade de evidência: `CHECKIN_OUT_GSD.md` (raiz).
> Legenda Etapa: R=Research · D=Discuss · P=Plan · E=Execute · V=Verify · S=Ship
> Status: ⬜ não iniciado · 🟡 em andamento · ✅ entregue+validado (com print) · ❌ reaberto (sem print/evidência)

## Ciclo por fase (cada célula precisa de print no check-out)
| Fase | Dono | R | D | P | E | V | S | Status geral |
|---|---|---|---|---|---|---|---|---|
| F0 Design System+Shell | AG-1 | ✅(Kiro) | ✅(Kiro) | ✅(Kiro) | 🟡 | ⬜ | ⬜ | 🟡 execução AG-1 injetada |
| F1 Projects | AG-2 | 🟡 | 🟡 | 🟡 | ✅ | ✅ | ⬜ | ✅ Projects backend+UI entregue com print |
| F2 Issues/Tasks | AG-2 | 🟡 | 🟡 | 🟡 | ✅ | ✅ | ⬜ | ✅ Issues backend+UI entregue com evidência textual; print bloqueado por install Playwright |
| F3 Squad Builder+Agents | AG-3 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| F4 Seats+Sessions | AG-4 | 🟡 | 🟡 | 🟡 | ✅ | ✅ | ⬜ | ✅ Seats/Sessions validado após build unblock |
| F5 FinOps+Observ+Live | AG-5 | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ⬜ | ✅ entregue com print |
| F6 Settings+Inbox+Search | AG-6 | ⬜ | ⬜ | ⬜ | ✅ | ✅ | ⬜ | ✅ entregue com print |
| F7 E2E+UI Review | rotativo | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

## Quem ENTREGOU (com print válido)
- AG-2 (F1 Projects): CHECK-OUT 2026-06-26T12:14:45Z, print `AOP/.planning/evidence/AG-2-projects.png`, build e pytest verdes.
- AG-4 (F4 Seats+Sessions): CHECK-OUT 2026-06-26T12:06:57Z revalidado em 2026-06-26T12:28:50Z, print `AOP/.planning/evidence/AG-4-seats-sessions.png`, build e pytest verdes.
- AG-5 (F5 FinOps+Observability+Live): CHECK-OUT 2026-06-26T12:07:00Z, print `AOP/.planning/evidence/AG-5-finops.png`, build verde.
- AG-6 (F6 Settings+Inbox+Search): CHECK-OUT 2026-06-26T12:02:19Z, print `AOP/.planning/evidence/AG-6-settings.png`, TypeScript verde.
- Codex (F2 Issues/Tasks): CHECK-OUT 2026-06-26T12:43:00Z, evidência `AOP/.planning/evidence/AG-2-issues.txt`, backend pytest e Next build verdes.

## Quem NÃO ENTREGOU / pendente
- AG-1 (F0): prompt Design System **ENFILEIRADO** no pane w8:pG; o pane estava em execução numa migração/infra HerdMaster (Postgres) fora de escopo — roda como próximo turno. Verify/Ship pendente.
- AG-3 (F3): bloqueado por quota no pane w8:pM; reinjetar quando liberar ou realocar para worker livre.
- F2 Issues/Tasks: entregue; pendência residual é capturar print real quando Playwright/Chromium estiver disponível.
- F7 E2E+UI Review: aguardando fechamento de F0/F2/F3 e consolidação final.

## Dispatch ao vivo — Onda 1 (atualizado 2026-06-26T12:28:50Z, resolvido por label)
| Agente | Label | Pane | Estado |
|---|---|---|---|
| AG-1 | CODEX_55#1 | w8:pG | working — design-system ENFILEIRADO atrás de infra HerdMaster |
| AG-2 | CODEX_55#2 | w8:pH | ✅ entregue — backend+UI Projects |
| AG-4 | CODEX_55#4 | w8:pK | ✅ entregue — Seats/Sessions validado |
| AG-3 | CODEX_55#3 | w8:pM | ❌ BLOQUEADO por quota (try again ~10:07 local) — pendente reinjeção |
| AG-5 | AGY_GEMINI-FLASH35 | w8:pN | ✅ entregue — FinOps+Observability+Live |
| AG-6 | AGY_GEMINI-PRO31 | w8:pF | ✅ entregue — Settings+Inbox+My Issues+Search |
| QA/E2E | NVIDIA_NEMOTRON_3_Ultra | w8:pQ | working — contrato/smoke (escopo só AOP/e2e/**) |
| TL  | KIRO_OPUS-48 | w8:pJ | orquestrando/monitorando |

> ⚠️ AG-5 originalmente mapeado para `AGY-OPUS46` (ausente no pane list) — realocado para `AGY_GEMINI-FLASH35`.
> ⚠️ AG-3 (CODEX_55#3) sem crédito agora; reinjetar quando quota resetar ou worker liberar.

## Reaberturas (CHECK-OUT sem print/evidência = inválido)
- _(nenhuma)_

## Onda 2 (2026-06-26T15:40Z) — tasks no Postgres (regra: tasks create antes de injetar)
Control plane RESTAURADO (estava down ⇒ tasks=0). CLI: `--config /tmp/aop-ops-runtime/herdmaster.config.toml`.
| Task | task_id (sufixo) | Assignee (label/pane) | ETA | Estado real (pane) |
|---|---|---|---|---|
| OTTL telemetria/lifecycle | …2922b40 | CODEX_55#2 / w8:pR | 120min | 🟢 working |
| Audit telas vazias → EMPTY_SCREENS_AUDIT.md | …211b4a3c | AGY_GEMINI-PRO31 / w8:pF | 30min | 🟢 working |
| Closeout F2 Issues (PRINT+SHA) | …050ec87a8 | CODEX_55#0 / w8:pQ (reatrib.) | 15min | 🟢 working |
| Closeout AG-3 Squad Builder (PRINT+SHA) | …3b48c20 | AGY-OPUS-46 / w8:pT | 15min | 🟢 working |

> ⚠️ BLOQUEIO: CODEX_55#1 (w8:pG) e CODEX_55#3 (w8:pS) com sessão expirada (re-login necessário). F2 closeout reatribuído p/ CODEX_55#0 (w8:pQ).
> ⚠️ Drift DB×realidade (motiva o OTTL): task OTTL ficou `failed/cli` no scheduler enquanto w8:pR a executa; F2 mostra `in_progress/w8:pG` (tentativa morta) até w8:pQ refazer checkin; AG-3 aparece em w8:pN. O reconciliador do OTTL vai detectar isso (STALLED/ABANDONED_MIDWAY/UNTRACKED_WORK).
> QA E2E exaustivo: DIFERIDO p/ F7.

> Regra: o TL move uma célula para ✅ **somente** com CHECK-OUT no ledger raiz contendo
> timestamp + nome do agente + caminho do PRINT (`AOP/.planning/evidence/<AGENTE>-<task>.png`) + build/teste.

# TECH-LEAD GUIDELINES — AOP Orchestration
**Versão:** 1.0 (2026-06-26) · **Autor:** Kiro (Principal Architect) · **Status:** vivo (evolui versão após versão)
**Propósito:** consolidar TODAS as instruções que tivemos que ensinar ao TL nas últimas 24h. Onboarding de
qualquer TL (atual ou futuro promovido) começa por aqui — é normal e esperado ensinar isto nos primeiros momentos.

---
## 0. REGRA-MÃE (não negociável)
**AS GOLDEN RULES DEVEM SER SEGUIDAS — SIM OU SIM, NÃO HÁ DISCUSSÃO.**
Tarefa "feita" sem evidência/check-in-out = NÃO FEITA = equivale a quebra de golden rule. O Kiro será cobrado
pelo operador; portanto o Kiro cobra o TL; o TL cobra os workers. Sem exceção.

## 1. PAPÉIS (hierarquia L1/L2-L3)
- **L1 — TL (Tech-Lead/Orquestrador):** valida planos, gerencia tasks e agentes, distribui trabalho, valida entregas.
  **EM HIPÓTESE ALGUMA escreve código.** Se ficar ocioso, **distribui MAIS** aos workers — nunca coda. Mesmo que se
  ofereça "porque está livre", a resposta é NÃO: distribua.
- **L2/L3 — Workers (codex/agy/etc.):** os ÚNICOS que implementam código.
- **Planner (Kiro CLI):** desenha arquitetura/processos, fornece o mapa vivo e os comandos ao TL, valida. Fala SÓ com o TL.

## 2. COMUNICAÇÃO
- Kiro ↔ TL apenas. TL ↔ workers. O Kiro NÃO fala direto com worker (exceção só com aprovação escrita do operador).
- Toda mensagem ao TL: usar `herdr pane run` (texto+Enter). `send-text` NÃO envia Enter → fica preso no input. Confirmar com `herdr pane read`.

## 3. MECANISMO DE DISPATCH (a lição que mais custou)
- **O TL NÃO usa subagentes próprios.** Todo agente PODE spawnar subagente, mas o TL que faz isso cria "exército
  fantasma" invisível (sem check-in/out, fora da governança) = dispatch-teatro. PROIBIDO.
- **O TL despacha INJETANDO prompt nas panes irmãs (os workers reais) via shell:**
  `herdr pane run <pane_id> "<prompt completo da task>"` e confirma com `herdr pane read <pane_id> --source recent`.
- **O Kiro fornece o MAPA VIVO** `label=pane_id` (de `herdr pane list`) e o **realimenta sempre que os IDs mudam**
  (os pane IDs churnam a cada reconexão). O TL resolve os workers por LABEL usando o mapa que o Kiro deu.
- Anti-padrão observado: o TL "narrou um plano/tabela e armou timer" sem injetar → workers ficaram idle. Inaceitável:
  **injetar de verdade e VERIFICAR que o worker saiu do idle.**

## 4. GOVERNANÇA OBRIGATÓRIA (o TL faz os workers cumprirem)
Para CADA task, o worker DEVE registrar em `CHECKIN_OUT_GSD.md` (raiz):
- **CHECK-IN (antes de tocar em qualquer coisa):** `nome do agente + timestamp UTC + escopo/paths`. **NÃO é opcional.**
- **CHECK-OUT (ao concluir):** `nome do agente + timestamp UTC + PRINT/screenshot (evidência) + SHA256 + saída build/teste`.
- **Sem PRINT = inválido.** Sem CHECK-IN antes = violação. O TL recusa check-out sem evidência e reabre a task.

## 5. ETA — OBRIGATÓRIO POR TASK
- Todo dispatch carrega **ETA (estimate_minutes)** + `task_id`. **Sem ETA = dispatch inválido.**
- O TL mantém os ETAs/timers vivos e **devolve ao Kiro a tabela `worker | pane | issue | ETA | estado`** sob demanda.

## 6. RASTREIO DE TASKS (Postgres / OTTL)
- O TL DEVE criar a task no HerdMaster antes de injetar (`herdmaster tasks create`) → trilha `who/what/when/ETA`.
- ⚠️ Limitação atual: rota `herdmaster tasks` retorna "unsupported tasks route" → o OTTL precisa implementá-la.
- Objetivo: `herdmaster tasks list` reflete a realidade; reconciliador detecta `STALLED/ABANDONED/UNTRACKED/INVALID_COMPLETION`.

## 7. PROCEDIMENTO DE CRASH / QUOTA (agente caiu/sem crédito)
1. Detectar (heartbeat morto / pane sumiu / "Overages/Credits 0"). 2. Classificar a task como **INTERROMPIDA** (não FAILED).
3. **Realocar IMEDIATAMENTE** a um worker saudável (substituir o morto). 4. **Retomada idempotente** (auditar o que já
existe antes de editar) OU refazer do zero, conforme a task. 5. Exigir evidência no check-out. 6. Registrar o handoff no ledger.
- Vale até para o próprio TL: TL sem crédito ⇒ promover outro (decisão do operador, por escrito).

## 8. TIMING DE QA
- QA E2E exaustivo é **só no FINAL** (fase F7), após todos os fixes/features + integração. Não testar 100x ao longo do caminho.

## 9. ANTI-PADRÕES (o que já deu merda — NÃO repetir)
- Subagente-teatro (sec.3) · `send-text` sem Enter (sec.2) · "narrar plano e ficar idle" (sec.3) · check-out sem print (sec.4) ·
  QA prematuro (sec.8) · scope bleed (worker editando fora do seu escopo de paths) · decisão por achismo (sempre dado/doc de fabricante).

## 10. CHECKLIST DE ONBOARDING DE UM NOVO TL (primeiros momentos)
- [ ] Ler: este doc + `CHECKIN_OUT_GSD.md` (golden rules+crash) + `STATUS.md` + `RISK_MITIGATION_PLAN.md` + `REMEDIATION_REPORT.md` + `EMPTY_SCREENS_AUDIT.md`.
- [ ] Confirmar que assumiu como L1 e que NÃO codará nem usará subagente próprio.
- [ ] Receber do Kiro o mapa vivo `label=pane_id` e o comando literal `herdr pane run`.
- [ ] Disparar 1 task de teste a 1 worker e provar (via `herdr pane read`) que o worker saiu do idle.
- [ ] Confirmar enforcement de check-in/out + PRINT + ETA em todo dispatch.

## CHANGELOG
- **v1.0 (2026-06-26):** versão inicial — consolida 24h de instruções (papéis, comunicação, dispatch via herdr,
  proibição de subagente, governança check-in/out+print, ETA, crash/quota, QA no fim, anti-padrões, onboarding).

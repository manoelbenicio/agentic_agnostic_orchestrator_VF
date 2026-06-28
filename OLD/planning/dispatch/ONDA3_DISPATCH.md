# ONDA 3 — DISPATCH PLAN (AGY_PRO TL)
**Data:** 2026-06-26T20:02Z | **TL:** AGY_PRO (substituiu KIRO_OPUS-48) | **Autorizado por:** Kiro planner

---

## SITUAÇÃO ATUAL (pós Onda 1+2)
- **Onda 1 FECHADA:** F0 (DS+Shell) ✅, F1 (Projects) ✅, F2 (Issues) ✅, F4 (Seats/Sessions) ✅, F5 (FinOps+Obs+Live) ✅, F6 (Settings/Inbox/MyIssues placeholders) ✅
- **Onda 2 FECHADA:** EMPTY_SCREENS_AUDIT ✅, Closeout F2 ✅, Closeout AG-3 ✅, OTTL (em andamento por CODEX_55#2)
- **GAPS IDENTIFICADOS (EMPTY_SCREENS_AUDIT + REMEDIATION_REPORT):**
  - `/inbox` = placeholder (setEvents([]))
  - `/my-issues` = placeholder (setIssues([]))
  - `/settings` = placeholder (setTimeout loading)
  - DB/pool sem robustez (R1/R2/R3 do RISK_MITIGATION_PLAN)
  - `herdmaster tasks` CLI retorna "unsupported tasks route" (rota existe no server.py:386-465 mas algo na comunicação CLI↔daemon falha)

## WORKERS DISPONÍVEIS (todos idle, resolver por LABEL)
| # | Label | Tipo | Nota |
|---|-------|------|------|
| W0 | CODEX_55#0 | codex | ✅ saudável |
| W1 | CODEX_55#1 | codex | ⚠️ sessão expirada — testar antes |
| W2 | CODEX_55#2 | codex | 🟡 pode estar no OTTL (verificar) |
| W3 | CODEX_55#3 | codex | ⚠️ sessão expirada — testar antes |
| W4 | AGY_Gemini-PRO31 | agy | ✅ saudável |
| W5 | AGY_FLASH35-HT | agy | ✅ saudável |

---

## ISSUES PARA DISPATCH (5)

### ISSUE 1 — Backend inbox_api + plugar /inbox
**Escopo:** Criar `AOP/control-plane/inbox_api/` (router+repository+schema+tests) + registrar rotas em `app/main.py` + plugar o frontend `AOP/web/src/app/inbox/page.tsx` e `components/inbox/inbox-view.tsx` para consumir API real (remover `setEvents([])`).
**Padrão:** seguir exatamente `projects_api/` ou `seats_api/` como referência (router+repository+tests).
**Backend endpoints:** `GET /inbox` (listar eventos), `POST /inbox/{id}/read`, `POST /inbox/bulk-archive`, `GET /inbox/unread-count`.
**Aceite:** pytest verde + npm build verde + curl /inbox retorna lista (vazia=ok) + UI consome real + PRINT+SHA.

### ISSUE 2 — Backend my-issues /api/issues/my + plugar
**Escopo:** Adicionar endpoint `GET /issues/my` em `AOP/control-plane/issues_api/` (filtrar por agent_id/assignee do contexto) + plugar frontend `AOP/web/src/app/my-issues/page.tsx` e `components/my-issues/my-issues-view.tsx` (remover `setIssues([])`).
**Backend endpoints:** `GET /issues/my?scope=all|assigned|created|my-agents`.
**Aceite:** pytest verde + npm build verde + curl /issues/my retorna lista + UI consome real + PRINT+SHA.

### ISSUE 3 — Backend settings_api + plugar /settings
**Escopo:** Criar `AOP/control-plane/settings_api/` (router+repository+schema+tests) + registrar rotas em `app/main.py` + plugar frontend `AOP/web/src/app/settings/page.tsx` e `components/settings/settings-view.tsx` (remover `setTimeout → setLoading(false)`).
**Backend endpoints:** `GET /settings` (ler config), `PATCH /settings` (atualizar), `GET /settings/profile`, `PATCH /settings/profile`.
**Modelo de dados:** tenant_id, general config, notification prefs, API tokens list, integrations, labs features.
**Aceite:** pytest verde + npm build verde + curl /settings retorna config + UI consome real + PRINT+SHA.

### ISSUE 4 — Robustez DB/pool no control-plane (R1/R2/R3 do RISK_MITIGATION_PLAN)
**Escopo:** No `AOP/control-plane/` e `HerdMaster/src/herdmaster/db/`:
- **(R1)** Garantir `conn.rollback()` em todo erro antes de reusar conexão; usar `with conn.transaction()` explícito; preferir `autocommit=True` onde aplicável.
- **(R2)** Configurar `check=ConnectionPool.check_connection` no pool → conexão ruim detectada e trocada; `reset` callback para limpeza.
- **(R3)** Implementar `reconnect_failed()` callback (alerta/restart) + `pool.wait()` no startup.
**Fontes vendor:** psycopg3 transactions [V1], psycopg3 pool [V2] — URLs em RISK_MITIGATION_PLAN.md.
**Aceite:** pytest verde + provocar conexão quebrada e verificar recovery automático + evidência textual + SHA.

### ISSUE 5 — OTTL: implementar rota `tasks` no daemon HerdMaster
**Escopo:** A rota `/tasks` JÁ EXISTE no `server.py:386-465` (POST create, GET list, checkin, complete, fail, progress). O problema: quando o CLI faz `herdmaster tasks checkin/complete/create`, a comunicação com o daemon retorna "unsupported tasks route". Investigar se:
  - (a) O daemon NÃO está rodando (e o CLI usa fallback que não tem tasks) — mais provável
  - (b) O roteamento CLI→socket não inclui `/tasks` em algum path
  - (c) A versão do daemon em runtime é antiga (sem a rota)
**Contexto:** CODEX_55#2 já recebeu esta task na Onda 2 (task-...2922b40). Verificar estado do trabalho dele (retomada idempotente).
**Ref:** `AOP/.planning/dispatch/REQUEST_ORCHESTRATION_TELEMETRY.md`
**Aceite:** `herdmaster tasks list --state running` retorna dados reais (não erro) + `herdmaster tasks create` funciona + PRINT+SHA.

---

## TABELA DE DISPATCH — WORKER × ISSUE × ETA

| Worker (LABEL) | Issue | Escopo | ETA | Crash Procedure |
|---|---|---|---|---|
| **CODEX_55#0** | #1 inbox_api + plugar /inbox | AOP/control-plane/inbox_api/**; AOP/web/src/app/inbox/**; AOP/web/src/components/inbox/**; app/main.py (só rota inbox) | 90min | Se crash: CODEX_55#3 assume; audit AOP/control-plane/inbox_api/** antes de editar; retomada idempotente |
| **AGY_Gemini-PRO31** | #2 my-issues /api/issues/my + plugar | AOP/control-plane/issues_api/** (add endpoint); AOP/web/src/app/my-issues/**; AOP/web/src/components/my-issues/** | 60min | Se crash: AGY_FLASH35-HT assume; audit issues_api/** antes de editar |
| **CODEX_55#1** | #3 settings_api + plugar /settings | AOP/control-plane/settings_api/**; AOP/web/src/app/settings/**; AOP/web/src/components/settings/**; app/main.py (só rota settings) | 90min | Se crash: CODEX_55#3 assume; retomada idempotente |
| **CODEX_55#3** | #4 robustez DB/pool (R1+R2+R3) | HerdMaster/src/herdmaster/db/**; AOP/control-plane/app/dependencies.py (pool config) | 120min | Se crash: AGY_FLASH35-HT assume; vendor docs psycopg3 obrigatórias |
| **CODEX_55#2** | #5 OTTL — rota tasks no daemon | HerdMaster/src/herdmaster/api/server.py; HerdMaster/src/herdmaster/cli.py; HerdMaster/src/herdmaster/db/repositories.py | 120min | Retomada da Onda 2 (task-...2922b40); se crash: CODEX_55#0 assume |
| **AGY_FLASH35-HT** | **RESERVA + VALIDAÇÃO** | Audita entregas conforme CHECK-OUTs; se qualquer worker crashar, absorve a issue. | contínuo | N/A |

---

## REGRAS DE CADA DISPATCH (embutidas no prompt do worker)
1. **CHECK-IN** obrigatório em `CHECKIN_OUT_GSD.md` (raiz) antes de tocar em qualquer arquivo.
2. **CHECK-OUT** com PRINT salvo em `AOP/.planning/evidence/<LABEL>-<issue>.png` + SHA256 + pytest/build output.
3. **Isolamento de paths:** cada worker escreve SÓ no seu escopo. Lê o resto read-only.
4. **Zero mock/placeholder:** empty state real consumindo API, não dados simulados.
5. **Vendor-grounded:** toda decisão técnica deve citar doc oficial (psycopg3, Next.js, FastAPI).
6. **Crash procedure:** se crash, novo worker audita o que existe e retoma de onde parou (regra idempotente).

## BLOQUEIOS CONHECIDOS
- **CODEX_55#1 e CODEX_55#3:** sessão expirada na Onda 2. Testar se re-logaram. Se ainda bloqueados, reatribuir #3 e #4 para AGY_FLASH35-HT.
- **CODEX_55#2:** pode ainda estar no OTTL da Onda 2. Verificar pane antes de reinjetar.

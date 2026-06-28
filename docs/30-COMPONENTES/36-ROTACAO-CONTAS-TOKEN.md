# 36 — Rotação Automática de Contas por Esgotamento de Token (janela de 5h)

> **Cenário (mapeado a pedido):** os agentes (Codex, Gemini, GLM, etc.) têm um **limite de tokens a cada ~5 horas**. Quando esgota, o agente **para na tela** com a mensagem do vendor ("limite atingido — deslogue e entre em outra conta ou compre créditos"). Como temos **várias assinaturas/contas**, o sistema deve **detectar o esgotamento, deslogar a conta atual, logar na próxima conta com tokens disponíveis e retomar a atividade** — automaticamente.
>
> **Status:** design/mapeamento. Reaproveita componentes existentes (`SeatPool`, `DeviceLoginService`, `QuotaAwareScheduler`/`QuotaLedger`). Implementação é trabalho de onda (ver doc 52). Há decisões em aberto no fim desta página.

---

## 1. Modelo conceitual

- Uma **conta** (assinatura de um vendor) = um **`Seat`** (`control-plane/seats/pool.py`), com **isolamento de credenciais** via `home_dir`/`config_dir` próprios (já usado pelo `DeviceLoginService`).
- Um **agente** trabalha "ocupando" um Seat (lease). Ao esgotar a quota daquele Seat, o agente **troca de Seat** (rotação), sem perder a tarefa.
- A quota é uma **janela deslizante de 5h** por conta: `tokens_per_window`, `window_start`, `tokens_used`, e `cooldown_until = window_start + 5h` quando esgota.

```
Pool de contas (por vendor)         Agente trabalhando
┌───────────────────────────┐       ┌──────────────────┐
│ conta-1 [EXHAUSTED] ⏳5h    │◀──────│ agente-X (lease) │
│ conta-2 [AVAILABLE] ✅      │──────▶│  rotaciona p/    │
│ conta-3 [AVAILABLE] ✅      │       │  conta-2         │
│ conta-4 [COOLDOWN]  ⏳2h    │       └──────────────────┘
└───────────────────────────┘
```

---

## 2. Detecção do esgotamento (dois sinais complementares)

### 2.1 Reativo — detector de "limite atingido"
- **Terminal (Herdr):** um **detector de padrão** lê a saída do pane e casa regex por vendor. Casou → mapeia para `QUOTA_EXHAUSTED` (ou `AgentState.BLOCKED` com `reason="quota"`).
- **Socket (HerdMaster/API):** resposta de quota/rate (HTTP **429**) → mesmo estado.
- Conecta no **monitor ~90s do TL** (doc 54): agente parado + padrão de quota = gatilho de rotação.

#### Padrões de esgotamento por vendor (pesquisados — confirmar contra a tela real no deploy)

Strings reais coletadas de relatos públicos (issues do GitHub/fóruns dos vendors). Cada empresa exibe um texto próprio; abaixo o padrão de detecção sugerido:

| Vendor | Texto que aparece (exemplos reais) | Regex sugerido (case-insensitive) | Fonte |
|--------|-----------------------------------|-----------------------------------|-------|
| **Codex** | *"You've hit your usage limit … try again at 3:51 PM"* / *"You've hit your usage limit, try again in 4 days …"* | `you've hit your usage limit` e `try again (at\|in)` | [openai/codex#3031](https://github.com/openai/codex/issues/3031), [ofox.ai](https://ofox.ai/blog/codex-weekly-limit-drained-2026/) |
| **Opus / Claude Code** | *"Claude usage limit reached. Your limit will reset at 2pm …"* / *"5-hour limit reached · resets 6am …"* / *"You've hit your limit for Claude messages …"* | `(usage limit reached\|5-hour limit reached\|hit your limit for claude)` e `reset` | [anthropics/claude-code#5977](https://github.com/anthropics/claude-code/issues/5977), [#12815](https://github.com/anthropics/claude-code/issues/12815) |
| **Antigravity (Google)** | *"You have reached the quota limit for this model. You can resume using this model at 2/1/2026, 3:36:33 PM …"* | `reached the quota limit for this model` e `resume using this model at` | [sonusahani.com](https://sonusahani.com/blogs/google-ai-pro-subscription-antigravity-quota), [discuss.ai.google.dev](https://discuss.ai.google.dev/t/here-is-how-to-fix-the-anti-gravity-quota-issues/132342/6) |

> *Conteúdo das mensagens foi resumido/reformulado para conformidade; confirmar a frase exata contra a tela real no primeiro deploy e ajustar o regex no `.env`.*

**Dois aprendizados importantes da pesquisa:**
1. **A mensagem geralmente traz o horário de reset** (ex.: "reset at 2pm", "resume … at 3:36 PM"). O detector deve **parsear esse horário** e usá-lo como `cooldown_until` exato, em vez de assumir 5h cheias. Todos os três têm **duas janelas** simultâneas (5h + semanal) — a conta pode esgotar pela semanal mesmo com 5h disponível.
2. **Nem todo "erro" é esgotamento de quota.** No Antigravity, **HTTP 503 "high traffic"** é problema do servidor do Google, **não** falta de quota — nesse caso **NÃO** rotacionar conta (desperdiçaria conta boa); apenas retry/trocar de modelo. O detector deve **distinguir 503/high-traffic de 429/quota**. Também há **bugs de falso-limite** (Codex "phantom limit") — daí a proteção de confirmação do §8.

### 2.2 Proativo — ledger de quota (preferível)
- O FinOps já grava **tokens por atribuição** (doc 35). Agregando por **conta/seat** na janela de 5h, dá para **rotacionar ANTES do hard stop** (ex.: ao atingir 95% do `tokens_per_window`).
- O `QuotaLedger` (redis) guarda por conta: `tokens_used`, `window_start`, `cooldown_until`. Evita a parada abrupta e o "agente travado queimando contexto".

> Recomendação: usar os **dois**. Proativo reduz interrupções; reativo é a rede de segurança quando o vendor corta antes do previsto.

---

## 3. Algoritmo de rotação (máquina de estados)

```
ON_EXHAUSTION(agente, conta_A):
  1. LOCK(agente)                         # evita rotação dupla
  2. ledger.mark_exhausted(conta_A, cooldown_until = reset_5h)
  3. snapshot = capturar contexto da tarefa (task_id, prompt, progresso, cwd)
  4. LOGOUT(conta_A) no runtime do agente  # comando de logout do vendor
  5. conta_B = pool.select_next(vendor, tenant, política)   # ver §5
        - se None: PARK(agente, status=waiting_quota,
                        wake_at = min(cooldown_until de todas))  → §6
  6. LOGIN(conta_B) via DeviceLoginService (HOME/config isolados)
        - aguardar até autenticado (poll status); falhou N vezes → marca conta_B degradada, tenta próxima
  7. RESTORE runtime (executor.restore) + RESUME tarefa (re-enviar prompt/continuação)
  8. tracing.record(rotation_event) + ledger.lease(conta_B, agente)
  9. UNLOCK(agente)
```

- **Retomada da tarefa:** snapshot do prompt/estado antes do logout; após login na conta_B, `executor.restore()` + re-dispatch da tarefa.
  > **Decisão (do produto):** ao trocar de conta, **o histórico/contexto da sessão é perdido** (é outra conta e não acompanha o histórico). Portanto a retomada é **reinício da tarefa a partir do prompt/checkpoint salvo**, não continuação do contexto vivo. O snapshot deve guardar o suficiente (prompt original + último checkpoint/artefato) para a conta_B recomeçar de forma útil. Aceita-se reprocessamento parcial.

---

## 4. Onde se conecta no código existente

| Peça | Arquivo | Mudança proposta |
|------|---------|------------------|
| Conta = Seat + quota | `seats/pool.py` | adicionar campos de janela (`tokens_per_window`, `window_start`, `tokens_used`, `cooldown_until`, `status`) e um `acquire` que **pula contas exhausted/cooldown** |
| Login/Logout isolado | `sessions_api/service.py` (`DeviceLoginService`) | já faz login isolado por vendor; **adicionar `logout(seat)`** e "aguardar autenticado" |
| Quota/seleção | `scheduler` (`QuotaAwareScheduler`/`QuotaLedger`) | rastrear janelas de 5h por conta e **escolher a próxima** disponível |
| Detecção | `executors/terminal.py` e `executors/socket.py` | detector de padrão (terminal) / mapear 429 (socket) → sinal `QUOTA_EXHAUSTED` |
| Estado | `core/models.py` (`AgentState`) | novo `QUOTA_EXHAUSTED` (ou `BLOCKED`+reason) |
| Observabilidade | `tracing` | evento de rotação na timeline do agente |
| Custo por conta | `finops` | incluir `account_id`/`seat_id` na atribuição → custo por conta (doc 35) |
| Identidade | `ops/sync_agent_identity.py`, `ops/agent-registry-reconcile.sh` | re-sincronizar identidade do agente após a troca |

> Observação: `DeviceLoginService` usa **device-login (OAuth)** com `HOME`/`config_dir` isolados por conta — é o caminho mais seguro (sem senha em disco). Já há `_vendor_env` para `codex`/`claude`/`gemini`/`kiro`.

---

## 5. Política de seleção da próxima conta

> **Decisão (do produto):** não há política de balanceamento (round-robin/LRU). A seleção é por **prioridade de expertise do modelo**. Ordem de prioridade fixa:
>
> 1. **Codex**
> 2. **Opus** (Claude)
> 3. **Antigravity**
> 4. demais vendors (fallback)
>
> Ou seja: ao precisar rotacionar, o sistema busca a **próxima conta disponível seguindo essa ordem de prioridade** (a melhor expertise primeiro), independentemente de qual conta foi usada por último. Só desce na lista quando as contas de maior prioridade estão todas esgotadas/cooldown.

Anticolisão: uma conta é **leased por um único agente** por vez (`SeatPool.ref_count` + lock), para dois agentes não drenarem a mesma conta simultaneamente.

---

## 6. Quando TODAS as contas estão esgotadas

- Os agentes entram em `waiting_quota` e o sistema agenda o **wake** para `min(cooldown_until)` (a conta que reseta primeiro).
- **ETA visível** no dashboard (quando cada conta volta) e **alerta via Alertmanager** ("pool de contas exausto, retorno em HH:MM").
- Ao resetar a janela, o agente **retoma automaticamente** sem intervenção.

---

## 7. Arquivo de contas (segurança)

> **Decisões (do produto):**
> - **Modo de auth: somente `device-login` ou `OAuth`.** Sem automação por usuário/senha (evita guardar senha e contorna MFA). O `DeviceLoginService` já suporta device-login por vendor.
> - **Armazenamento:** **temporariamente no `.env`** (referências/tokens de device-login), com **migração futura** para um cofre seguro (sops/age/keyring/Vault). Migração **não é prioridade agora**.

Recomendações enquanto estiver no `.env`:
- **NÃO** versionar o `.env` no git e **não logar** valores de token.
- Como é device-login/OAuth, o que vive no `.env`/`config_dir` é **token de sessão**, não senha — risco menor.
- Cada conta tem `home_dir`/`config_dir` isolado (já implementado), então as sessões não se misturam.
- Marcado como **dívida**: migrar segredos do `.env` para cofre antes de produção (ADR-009).

Formato sugerido (reusa `AOP_SEATS_FILE`/`AOP_SEATS_JSON`), exemplo TOML:
```toml
[[seats]]                       # uma entrada por conta
seat_id = "codex-acct-1"
tenant_id = "tenant-1"
vendor = "codex"
home_dir = "/srv/aop/seats/codex-acct-1"   # isolado, fora de /tmp
auth_mode = "device"                        # device-login / OAuth (somente)
priority = 1                                # 1=Codex, 2=Opus, 3=Antigravity (ver §5)
tokens_per_window = 5000000                 # cota da janela de 5h (varia por conta/plano — ver §6)
window_seconds = 18000                      # 5h
```

---

## 8. Modos de falha e proteções

| Falha | Proteção |
|-------|----------|
| Falso positivo de detecção | exigir padrão explícito + estado persistente por > X s antes de rotacionar |
| Login da nova conta falha (MFA, creds expiradas) | marcar conta `DEGRADED`, pular para a próxima, alertar |
| Thrash (rotação em loop) | limite de N rotações por tarefa/janela; se exceder → park, não girar |
| Duas tarefas na mesma conta | lease único por conta (`SeatPool` + lock) |
| Perda de contexto no logout | snapshot de prompt/checkpoint antes; **reiniciar** a tarefa na conta nova (contexto não é portável entre contas) |
| Todas exaustas | park + ETA + alerta; retoma no reset |

---

## 9. Observabilidade / KPIs

- `aop_accounts_total{vendor,status}` (available/exhausted/cooldown)
- `aop_account_rotations_total{vendor,reason}` e tempo médio de rotação
- `aop_agent_parked_seconds_total` (tempo perdido aguardando quota)
- custo e tokens **por conta** por janela (extensão do FinOps, doc 35)
- Dashboard: saúde do pool + contagem regressiva de cooldown por conta.

---

## 10. Decisões — status

| # | Pergunta | Decisão |
|---|----------|---------|
| 1 | Mensagem/erro exato de esgotamento por vendor | ✅ **PESQUISADO** (ver §2.1): Codex `"you've hit your usage limit"`, Claude `"usage limit reached / 5-hour limit reached … resets"`, Antigravity `"reached the quota limit for this model … resume … at"`. Confirmar a frase contra a tela real no 1º deploy e ajustar regex no `.env`. |
| 2 | Modo de auth | ✅ **device-login / OAuth somente** (sem usuário/senha) |
| 3 | Perda de contexto no logout | ✅ **perde o contexto** → retomada = reinício a partir do prompt/checkpoint |
| 4 | Política de seleção | ✅ **sem balanceamento**; prioridade por **expertise do modelo**: Codex → Opus → Antigravity → fallback |
| 5 | Armazenamento de credenciais | ✅ **`.env` por enquanto**; migrar p/ cofre depois (dívida, sem prioridade) |
| 6 | Cota por janela | ✅ **janela de 5h × N milhões de tokens**, configurável **por conta** (`tokens_per_window`/`window_seconds`) — cada empresa/plano tem a sua |

### Único item aberto
Nenhum bloqueante. A **pergunta 1 foi resolvida por pesquisa** (§2.1) — só falta **confirmar a frase exata contra a tela real** no primeiro deploy e ajustar o regex no `.env` (não bloqueia o design nem a implementação). O design está **fechado** e pronto para implementação em onda (reaproveitando `SeatPool` + `DeviceLoginService` + `QuotaLedger`).


---

## 11. Esqueleto implementado (módulo `control-plane/rotation/`)

Esqueleto **criado e testado** (52 testes verdes no total; 19 do próprio módulo). Isolado: importa sem depender do HerdMaster e **não altera o fluxo atual** (só é construído se `AOP_ROTATION_ENABLED=true`).

| Arquivo | Conteúdo | Estado |
|---------|----------|--------|
| `rotation/models.py` | `Account` (=Seat+quota), `AccountStatus`, `RotationReason`, `TaskSnapshot`, `RotationOutcome`, `VENDOR_PRIORITY` (codex=1, opus/claude=2, antigravity=3) | ✅ completo |
| `rotation/detector.py` | `QuotaExhaustionDetector`: regex por vendor (override `AOP_QUOTA_PATTERNS_JSON`), `detect_text`, `detect_status_code` (429=quota, 503=overload→não rotaciona), `parse_reset_time` (relativo / clock / datetime) | ✅ completo |
| `rotation/pool.py` | `AccountPool`: seleção por prioridade de expertise + maior quota, lease único, `mark_exhausted`/cooldown, `next_wake_at` (ETA), `refresh_windows` (reset) | ✅ completo |
| `rotation/auth.py` | `DeviceLoginAuthenticator` sobre `DeviceLoginService`: `login`(`start`), `wait_authenticated`(poll `status`), `logout` (comando por vendor via `AOP_LOGOUT_COMMANDS_JSON`, env isolado) | ✅ completo |
| `rotation/service.py` | `AccountRotationService.on_exhaustion(...)`: máquina de estados (lock, anti-thrash, mark, logout, seleção+login c/ retry, resume hook, park c/ ETA) | ✅ completo |
| `rotation/assembly.py` | `account_from_record`, `build_account_pool`, `build_rotation_service` (carrega contas do mesmo formato de seats) | ✅ completo |
| `app/settings.py` | flags `rotation_enabled`, `rotation_login_timeout_s`, `rotation_max_rotations_per_window`, `rotation_logout_commands_json` | ✅ |
| `app/dependencies.py` | `_build_rotation_service()` + `AppState.rotation_service` (opcional, guardado pela flag, à prova de falha) | ✅ |

### Pontos de extensão — status

| # | Item | Estado |
|---|------|--------|
| 1 | **Gatilho de detecção no dispatch** — `collect_events` detecta esgotamento por evento (`rotation/trigger.py::exhaustion_from_event`) e dispara a rotação | ✅ **escrito** (guardado por `rotation_service` + `task.account_id`) |
| 2 | **Resume** — após rotação, a tarefa é **re-disparada (restart)** na conta nova, com marcador no stream de eventos | ✅ **escrito** (loop em `collect_events`, limitado por anti-thrash) |
| 3 | **`logout` por vendor** — definir comandos reais em `AOP_LOGOUT_COMMANDS_JSON` | ⚙️ **config no deploy** (código pronto) |
| 4 | **Persistência multiprocesso** — mover `_locks`/`_rotation_counts` p/ redis/`QuotaLedger` | 🔜 onda (com >1 worker) |
| 5 | **Métricas** — expor contadores do §9 no `/metrics` | 🔜 onda |
| 6 | **Aquisição de conta no dispatch** — popular `task.account_id` com a conta leasada (hoje vem do request; ligar ao `AccountPool.lease` no início do dispatch) | 🔜 onda |

> Com o gatilho (1) e o resume (2) escritos, o caminho fim-a-fim está **codificado**: detectar → rotacionar por prioridade → re-disparar. Como `AOP_ROTATION_ENABLED=false` por padrão e o gatilho só age quando `task.account_id` está setado, **o fluxo atual permanece idêntico** até a squad ligar a flag e popular o pool de contas.

### Como o gatilho enxerga o esgotamento
`exhaustion_from_event` (em `rotation/trigger.py`) inspeciona cada evento serializado:
- `message` (texto livre do evento),
- `details["queue"]` (registro do HerdMaster: `state`/`error`/`message`),
- `details["status_code"]` / `http_status` (429 = quota → rotaciona; 503 = overload → **não** rotaciona),
- `details["pane_text"]`/`output`/`stdout` (captura do pane em terminal-mode).

> Para o terminal-mode funcionar 100%, o `TerminalExecutor` precisa **incluir a captura do pane** (`details["pane_text"]`) nos eventos — pequeno ajuste no executor, listado como item da onda. Em socket-mode, basta o HerdMaster propagar `status_code`/mensagem no registro da tarefa.

### Pontos de extensão que faltam para "100% no ar" (onda de implementação)
Ver a **tabela de status** acima (itens 3–6). Resumo: configurar `logout` por vendor, persistir guardas em redis, expor métricas e ligar a aquisição de conta no início do dispatch (popular `task.account_id`). Gatilho (1) e resume (2) já estão escritos.

### Checklist de deploy do cenário de rotação
- [ ] Definir o **pool de contas** em `AOP_SEATS_FILE`/`AOP_SEATS_JSON` (uma entrada por conta, com `priority`/`tokens_per_window`/`window_seconds`).
- [ ] Definir `AOP_DEVICE_LOGIN_COMMANDS_JSON` (device-login por vendor) e `AOP_LOGOUT_COMMANDS_JSON` (logout por vendor).
- [ ] Confirmar a **frase de esgotamento** real de cada vendor e ajustar `AOP_QUOTA_PATTERNS_JSON` se preciso (doc §2.1).
- [ ] Conectar `resume_hook` + gatilho de detecção (itens 1 e 2 acima).
- [ ] `AOP_ROTATION_ENABLED=true`.
- [ ] Validar com 1 conta esgotando de verdade → troca para a próxima por prioridade → tarefa retomada.

> Enquanto `AOP_ROTATION_ENABLED=false` (padrão), nada muda no comportamento atual — o módulo fica disponível mas inerte.

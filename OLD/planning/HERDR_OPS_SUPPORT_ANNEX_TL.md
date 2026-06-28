# 🛠️ HERDR OPERATIONS SUPPORT ANNEX — para o TL (KIRO_OPUS-48)
**Anexo do** `MASTER_DELIVERY_PLAN_TL.md` · **Data:** 2026-06-27 · **Herdr:** 0.7.1 (verificado `herdr --version`)
**Escopo:** como o Herdr se comporta no dia-a-dia da orquestração — detecção de estado, dispatch,
verificação, recuperação e reset por harness. **Tudo aqui foi testado AO VIVO nesta máquina** (WSL2/Ubuntu),
não é teoria. Alimenta diretamente as tasks OpenSpec **3.2** (adapters nativos + estado semântico) e
**3.3** (fallback screen-scrape), e a operação de despacho das ondas do plano-mestre.

---

## 0. Frota real (roster vivo, `herdr pane list`)
Três harnesses — o modelo por trás é irrelevante p/ o Herdr (ele detecta o CLI):
- `codex` = OpenAI Codex CLI · `agy` = **Antigravity = Google = Gemini** (label único `agy`) · `kiro` = Kiro/AWS.
- Labels distintos confirmados: `['agy','codex','kiro']`. **Não existe pane Claude Code** nesta frota.
- IDs de pane no formato **`w<N>:p<X>`** (ex.: `w8:pQ`) — herdr 0.7.x, estáveis; SKILL.md mostra `1-1` (formato antigo). **Sempre reler IDs de `pane list`, nunca hardcodar.**

## 1. Modelo de autoridade de estado (impacta o adapter — task 3.2)
- Toda a frota é **screen-manifest** (sem lifecycle hooks). Codex/Claude/Cursor/Copilot/Droid/Qoder = integração só de **session-identity** (estado vem do screen manifest). AGY e Kiro = **sem integração alguma**.
- Lifecycle-authority (hooks autoritativos) existe SÓ p/ Pi, OMP, Kimi, OpenCode, Kilo, Hermes. **Nenhum dos nossos 3 vira lifecycle authority** → o adapter nativo (3.2) deve depender de **manifest/screen detection**, não de hooks.
- `blocked` é estrito: só marca quando o bottom-buffer casa uma UI conhecida de aprovação/permissão. Sem regra → cai em `idle` rotulado **`default_known_agent_idle_fallback`** (idle "chutado", não confiável).

## 2. Detecção de estado: manifests + overrides locais (ENTREGUE nesta sessão)
**Fonte da verdade do schema:** manifests reais em `~/.local/state/herdr/agent-detection/remote/*.toml`.
**Override local:** `~/.config/herdr/agent-detection/<agent>.toml` — **REPLACE total** do ruleset (não merge).

### Schema de regra (verificado em arquivo real)
- Top-level: `id`, `version` (**DOTTED-NUMERIC obrigatório** — sufixo tipo `-local.1` é REJEITADO no load), `min_engine_version`, `updated_at`, `aliases[]`.
- `[[rules]]`: `id`, `state` (`idle|working|blocked|unknown`), `priority` (int, **maior vence**), `region` (`osc_title|whole_recent|after_last_prompt_marker|bottom_non_empty_lines(N)`), `visible_idle|visible_working|visible_blocker`, `skip_state_update`.
- Matchers: `contains[]`, `regex`, `line_regex[]`, `any=[{..}]` (OR), `all=[{..}]` (AND), `not=[{..}]` (negação); aninham.

### Root cause que corrigimos
AGY e Kiro tinham regras só de `working`+`blocked` (SEM regra de idle) → prompt pronto não casava nada → fallback-idle. Codex tinha idle só via `osc_title`, que observamos **vazio** (startup E in-session) → fallback.

### Overrides instalados (idle agora rule-matched p/ os 8 panes)
| Harness | arquivo | regra idle nova | assinatura (capturada live `pane read --source detection`) |
|---|---|---|---|
| agy | `~/.config/herdr/agent-detection/agy.toml` | `ready_prompt_idle` @prio50 | `contains ["? for shortcuts"]` |
| kiro | `~/.config/herdr/agent-detection/kiro.toml` | `ready_prompt_idle` @prio50 | `contains ["ask a question or describe a task"]` |
| codex | `~/.config/herdr/agent-detection/codex.toml` | `live_idle` @prio50 | `line_regex ['gpt-[0-9.]+\s+\w+\s+·\s+/']` (footer modelo·cwd) |
- Cada override = **ruleset remoto completo (verbatim) + 1 regra idle prio50** (baixa, p/ working/blocked vencerem). `version` `.99` marca fork local.
- Masters versionados no repo: `HerdMaster/ops/herdr-overrides/staging/{agy,kiro,codex}.toml`.
- Aplicar/recarregar: `herdr server reload-agent-manifests` → conferir `source_kind: "local override"` e **sem `warning`**.
- **Rollback:** `rm ~/.config/herdr/agent-detection/<agent>.toml && herdr server reload-agent-manifests` (remoto/bundled volta).

### Verificação (autoridade) — use SEMPRE `agent explain --json`
`herdr agent explain <pane> --json` retorna chaves reais: `state`, `matched_rule{id,...}|null`, `fallback_reason|null`, `evaluated_rules[]`, `manifest_source`, `local_override_shadowing_remote`.
- **CLEAN** = `state` idle/done **com `matched_rule` e sem `fallback_reason`**.
- `idle + fallback_reason` = NÃO confiável (Herdr chutou). Pós-override, os 8 panes dão matched_rule (zero fallback) — provado live.

> **Comandos `herdr server` reais (ausentes do CLI Reference público, mas existem no binário):**
> `agent-manifests [--json]`, `update-agent-manifests [--json]`, `reload-agent-manifests`.

## 3. Dispatch confiável (impacta o executor Terminal — D4/task 2.3)
- `herdr pane run <pane> "<cmd>"` = **texto + Enter** (submete). É o primitivo de dispatch.
- `herdr pane send-text <pane> "<txt>"` = texto literal **sem** Enter.
- `herdr pane send-keys <pane> <key>` = teclas; **tokens minúsculos**: `enter`,`esc`,`ctrl+u`,`shift+tab`,`f1`,`minus`,`plus` (legado `C-c`/`c-c` aceito). NÃO aceita `prefix+`.
- **Reset de contexto por harness (comportamento OBSERVADO de cada CLI, não doc Herdr):**
  - `codex` → **`/new`** (PROVA live: o pane mostrou `Unrecognized command '/chat'. Type "/" for a list` ×3 → codex rejeita `/chat new`).
  - `agy` / `kiro` → **`/chat new`**.

## 4. ⚠️ Achado crítico de waits (impacta qualquer "settle" no scheduler/executor)
- `herdr wait agent-status <pane> --status <s> --timeout <ms>`: exit **0 = match**, **1 = timeout** (confirmado live).
- `--status working` e `--status done` funcionam para transições.
- **`--status idle` é NÃO-CONFIÁVEL p/ agentes screen-manifest** (agy/kiro): deu timeout até sobre uma transição working→idle COMPROVADA por polling. Não é level-triggered confiável p/ idle.
- **Regra operacional:** para "esperar assentar em idle", **NÃO** use `wait agent-status idle`. Faça **poll de `agent explain --json`** (rastreia idle/working com precisão e instantâneo). Isso já está aplicado no `bootstrap.sh`.

## 5. `agents-flush` (reset em massa verificado) — `HerdMaster/ops/bootstrap.sh`
Fluxo por pane (testado live nos 8): carrega roster vivo → reset por tipo (`/new` codex, `/chat new` demais) via `pane run` → `wait_pane_settle` (**poll de explain**, não wait-idle) → verificação por `agent explain` (autoridade ÚNICA) → recovery se suspeito.
- **Recovery de pane preso** (ex.: palette `/` do codex engolindo Enter): `send-keys ctrl+u` → `esc` → `ctrl+u` → re-`pane run` → re-verifica.
- **2 bugs corrigidos via teste real:** (1) `wait_pane_settle` usava `wait agent-status idle` (queimava timeout) → trocado p/ poll-explain; (2) o gate exigia read-back de texto, mas o eco do comando pós-reset dava falso-suspeito → `agent explain` virou autoridade única, read-back só informativo, +branch `blocked`.
- Resultado: 8/8 panes `limpo` via explain, zero falso-suspeito.

## 6. Como isto alimenta o plano-mestre (ondas)
- **Task 3.2 (adapters nativos + estado semântico):** o moat é exatamente a técnica desta seção — manifests por vendor + `agent explain` como leitura de estado. Os 3 overrides já são a v0 dos adapters de estado de codex/agy/kiro. Generalizar: 1 manifest por vendor, `region`/`contains`/`line_regex` calibrados por captura `--source detection`.
- **Task 3.3 (fallback screen-scrape):** é o caminho `whole_recent` + heurística de footer (ex.: `live_idle` do codex) — reaproveitar.
- **Operação das ondas:** o TL despacha tasks via `pane run`, confirma execução por `agent explain` (não por exit code do subprocess), usa `agents-flush` p/ resetar contexto entre fases, e o `wait_pane_settle` (poll-explain) p/ saber quando um agente assentou.
- **Governança 15.x:** o ledger `CHECKIN_OUT_GSD.md` + evidência casam com a recomendação de não confiar em auto-report de agente — confirmar sempre por comando/`agent explain`/print.

## 7. Ambiente / WSL (impacta NFR de observabilidade e notificações)
- WSL2/Ubuntu, WSLg ativo (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`), **`notify-send` AUSENTE**.
- Notificação Herdr: `[ui.toast] delivery="terminal"` é o caminho que funciona aqui (`system` falharia sem notify-send). `agent_panel_sort="priority"` já configurado. `config.toml` validado (`reload-config` → applied).
- `[experimental] pane_history=true` grava conteúdo de panes (possíveis segredos) em `~/.config/herdr/session-history.json` — fora do repo (sem exposição git), mas ciente.
- Integração codex atualizada **v5→v6** (`herdr integration install codex`, idempotente) → restore de sessão `codex resume <id>` após restart do *servidor* Herdr (NÃO é autoridade de estado).

## 8. Referências (documentação completa desta base operacional)
`AOP/docs/PROCESS_NOTES_2026-06-26.md` (seções 8e–8k: dispatch/tokens, schema de manifesto, overrides, testes live) ·
`AOP/docs/RESEARCH_BRIEF_HERDR_OPEN_QUESTIONS_2026-06-26.md` (Q1–Q12 + addenda + LIVE TEST REPORT) ·
`HerdMaster/ops/bootstrap.sh` (`agents-flush`, `wait_pane_settle`, overrides) ·
`HerdMaster/ops/herdr-overrides/staging/{agy,kiro,codex}.toml` + `HerdMaster/ops/herdr-overrides/SKILL.md` ·
docs oficiais Herdr (Agents/Socket API/Integrations/Configuration) consolidadas nos arquivos `HerdMaster/docs/HERDR_*_OFICIAL.md`.

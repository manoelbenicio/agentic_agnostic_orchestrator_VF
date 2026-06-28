# Process Notes — Registry Integrity, Backups & DB Consolidation (real-time journal)

Sessão de 2026-06-26 (America/Sao_Paulo). Diário do raciocínio e das ações em tempo real —
o que foi observado, decidido, o porquê, surpresas e evidências. Mantido a pedido do operador.

---

## 0. Contexto inicial
Continuação de uma sessão de orquestração (Tech-Lead com fan-out p/ panes do herdr). Cheguei com
um log onde o agente anterior tinha "consertado" o DB recriando `hm_main` vazio e populando
`hm_main.agents` à mão a partir do `herdr pane list`. Em vez de seguir despachando, parei para
**verificar a fundação** — instinto certo, como se provou.

## 1. Primeiro red flag — o "fix" de DB do agente anterior
- Verifiquei schemas: só `hm_main` (8 tabelas) e `public`. O schema `hm_test_*` que ele citou
  havia sumido.
- Logs do Postgres: `drop schema ... cascade` em loop sobre todos `hm_test_%` (rotina de teardown
  de teste). Conclusão: o dado perdido era efêmero de teste — **confirmado depois pelo operador**.
- Lição: "tasks list retorna []" foi celebrado como "DB operacional" pelo agente anterior, quando
  na verdade era um schema **novo e vazio**. Vazio ≠ saudável.

## 2. Agents table dessincronizada (steering: "atualize agentes/panes conforme prints")
- Cruzei `herdr pane list` (fonte de verdade) com os screenshots. 3 panes com identidade ERRADA na
  tabela (`w8:p12`, `w8:p14`, `w8:pG`) — população anterior usou snapshot antigo.
- Ressincronizei via upsert idempotente. Decisão consciente: **não** apagar tasks/estado, só
  corrigir label/type/pane.

## 3. Backup inexistente (operador, com razão, irritado)
- Decisão de ordem: **backup ANTES de qualquer drop**. Implementei `AOP/ops/db-backup.sh`
  (full|hourly, `-Fc`, verificação com `pg_restore --list`, retenção 8/48), `db-restore.sh`,
  `install-backup-cron.sh`.
- Escolha técnica: snapshots horários full-lógicos (cada um restaurável de forma independente) em
  vez de WAL/PITR — porque PITR exige restart do Postgres (disrupção) e o DB é minúsculo. PITR
  fica como upgrade opcional documentado.
- Cron: hourly :05 + full domingo 03:00; daemon habilitado no systemd (persiste reboot do WSL).

## 4. Classificação canônico vs órfão (a parte que evitou desastre)
- O operador autorizou "deletar tudo antigo sem rastreabilidade". Mas deletar às cegas mataria
  schemas de produto.
- **Prova por código**: cada módulo do control-plane gera o nome do schema como
  `aop_<mod>_<sha1("aop_<mod>")[:12]`. Computei os hashes → bateram 100% com os 10 `aop_*` no DB.
  Logo, os 10 `aop_*` + `hm_main` são **canônicos**; os 22 `ag2_*/ag3_*/ag4_*` são cópias de
  evidência/teste criadas por agentes (sem correspondência no código) = **órfãos**.
- Full backup imediato (continha os 33 schemas) → drop dos 22 com guarda anti-canônico →
  restaram exatamente 11 canônicos + public. Control-plane seguiu `status:ok`.

## 5. Grafana (steering: URL + "broken" + 8 prints)
- `ERR_CONNECTION_REFUSED` na 3000: containers de observabilidade usam `network_mode: host` e
  escutam em `*:3000` dentro da VM WSL; o WSL2 não encaminha isso ao localhost do Windows.
  Fix imediato: acessar via IP do WSL `172.19.77.147:3000` (confirmado pelo operador).
- Os 8 prints revelaram o achado-chave: **Registry Integrity = VIOLADO, Ghost Agents = 8,
  Actual 9 vs Expected 7**.

## 6. Root cause dos "ghost agents" (o coração do dia)
Rastreei a métrica `herdmaster_whitelist_compliant`/`unlisted`/`expected` até a fonte. Havia uma
**whitelist hardcoded OBSOLETA do workspace antigo `w6:*`** em TRÊS lugares:
  1. `HerdMaster/deploy/observability/remediation/webhook_server.py` (`AGENT_WHITELIST`)
  2. `HerdMaster/src/herdmaster/api/server.py` (`_AGENT_WHITELIST`, exporter das métricas)
  3. Comentário em `prometheus/alert_rules.yml`
O roster real é `w8:*`. Por isso TODO agente atual era "unlisted". Pior: havia um **auto-purge**
(Alertmanager → `/webhook/remediate` → `purge_unlisted_agents()`) que DELETA via API qualquer
agente fora da lista `w6` — o sistema **se auto-sabotava**. (E ainda usava token `admin` ≠ token
real do config, então o purge provavelmente 401-ava — sorte que não apagou de vez.)

## 7. Decisão de design (steering: "flush purge clean + serviço 1h/1h")
Em vez de trocar uma lista hardcoded por outra (que envelheceria de novo), tornei a whitelist
**dinâmica e derivada do roster vivo**:
- `AOP/ops/agent-registry-reconcile.sh`: deriva roster do `herdr pane list` (+`cli`), escreve a
  whitelist canônica em `~/.config/herdmaster/agent_whitelist.json`, faz upsert dos nomes corretos
  e **prune** de qualquer agente fora do roster. Modo `--flush` zera runtime (tasks/audit/alerts/
  messages/health_events) + registry para slate limpo. FK rules (CASCADE/SET NULL) tornam o prune
  seguro.
- `server.py` e `webhook_server.py` agora **leem esse arquivo** (fallback seguro). Fonte única.
- Cron horário (:15) roda o reconciliador → o sistema se autocorrige e não é "induzido ao erro".
- Sub-agents: optei por sequencial — flush/whitelist/reconciler tocam o MESMO estado mutável
  (tabela agents, arquivo whitelist, webhook_server.py); paralelizar colidiria.

## 8. Execução & evidências
- `--flush`: 9 agents corretos (cli + 8 panes w8), ghost=0, runtime zerado, registry limpa.
- Restart fiel do herdmaster (pipx editable) → exporter recarregado:
  `agents_total=9, expected_total=9, unlisted=0, whitelist_compliant=1`.
- Recriei o container de remediation → log: `Whitelist (9 agents): [cli, w8:p12, ...]`.
- Reconcile em modo normal: idempotente (`db_agents=9 ghost=0`).
- Prometheus targets: `herdmaster-internal-metrics up`, `herdmaster-remediation up`,
  `herdmaster-e2e-api-monitor up`. Control-plane `status:ok, coupling connected`.

## 8b. "Ainda vejo dado velho" (steering) — investigação + correções residuais
O operador mandou 2 prints do **herdr TUI** (não Grafana) com nomes velhos (`CODEX_55#1 w8:pG`,
`AGY_FLASH35-HT w8:p12`). Diagnóstico: esse texto está **dentro do pane do AGY_OPUS46** — é a
saída/narração congelada daquele agente (contexto dele), que NÃO se atualiza a partir do registro.
Verifiquei as fontes vivas e estão todas limpas (9 nomes corretos):
- `GET :8080/agents` (API, fonte dos dashboards) ✓
- `herdr pane list` ✓
- `hm_main.agents` (DB) ✓
- métricas de integridade ✓

A caça por referências antigas persistidas achou 2 itens reais e os tratei:
1. **Remediation com token errado** (`HERDMASTER_TOKEN=admin` ≠ token real `39e0fb89…`) → auto-purge
   daria 401. Corrigido: webhook lê token de arquivo (`/herdmaster-data/herdmaster.token`,
   resolvido a cada request); o reconciliador espelha o token vivo de hora em hora; env
   `HERDMASTER_TOKEN_FILE` no compose. **Verificado**: remediate manual → autenticou, `deleted=0`,
   log `purge_noop/clean` (não 401).
2. **`~/.config/herdmaster/config.toml` stale** (não usado pela instância viva, que é
   `/tmp/aop-ops-runtime/...`): tem `agent_allowlist` w8 com panes inexistentes (pN/pF/pM/pH/pK) e um
   "Mapeamento Oficial" marcado **"NÃO trocar"** que CONFLITA com o herdr vivo
   (diz w8:pJ=KIRO/TL, w8:pG=CODEX_55#1; herdr vivo diz w8:pJ=AGY_OPUS46, w8:pG=KIRO_OPUS48).
   **Não editei** (respeitei o marcador) — PENDENTE decisão do operador sobre qual é a verdade.

## 8c. "Ainda vejo dados velhos e errados" (2º steering) — a FONTE persistente
Os prints mostravam a tabela impressa DENTRO do pane do AGY_OPUS46 (`w8:pG=CODEX_55#1`,
`w8:p12=AGY_FLASH35-HT`) — saída congelada do contexto daquele agente, não dado vivo. Usei 2
sub-agents (auditor independente + sweeper) que confirmaram: **estado vivo 100% limpo** (11 schemas,
9 agents, compliant=1, backups, cron) e localizaram a FONTE persistente dos nomes errados:
- **`HerdMaster/ops/bootstrap.sh` (HIGH / landmine)**: `AGENT_MAP` obsoleto (w8:pJ=KIRO/TL,
  w8:pG=CODEX_55#1) + `purge_unlisted_agents()` com whitelist `(cli,w8:pJ,pQ,pN,pF,pG,pM,pH,pK)` —
  panes pN/pF/pM/pH/pK NEM EXISTEM. Rodar `bootstrap.sh start/restart` **deletaria os 5 agentes
  reais** (pY,p14,pS,pR,p12). Corrigido: AGENT_MAP alinhado ao roster vivo; purge passa a LER a
  whitelist dinâmica (`agent_whitelist.json`) com fallback seguro ao roster vivo.
- `AOP/ops/status360.py`: labels stale (CODEX_55#1/AGY-OPUS-46/etc.) → nomes vivos.
- `prometheus/alert_rules.yml`: comentário w6 → descrição da whitelist dinâmica.
- `HerdMaster/.tmp_config.toml`: leftover stale → removido.
Verificado: `grep` dos identificadores obsoletos nos arquivos ops ativos = CLEAN; sintaxe OK.
Limite honesto: NÃO dá para reescrever o scrollback de outro agente vivo; para o pane do AGY_OPUS46
exibir certo, aquele agente precisa de refresh de contexto (`/chat new` via herdr / re-pull).

## 8d. Automação total da identidade + flush de contexto (3º steering)
Operador pediu: resolver o flush E criar uma função para que `config.toml` e tudo mais seja
atualizado DINAMICAMENTE, nada manual.
- **`AOP/ops/sync_agent_identity.py`** (fonte única): deriva o roster do `herdr pane list` (+cli) e
  propaga para TUDO, idempotente: (1) whitelist JSON; (2) espelho do token do control-plane;
  (3) `agent_allowlist` em TODO config.toml (live `/tmp/...` + `~/.config/...`) — insere sob
  `[watchdog]` se faltar; (4) bloco de comentário "managed agent map" auto-gerado entre marcadores.
  Substituiu a allowlist obsoleta (w6/pN/pF/pM/pH/pK) pela lista viva nos dois configs.
- **Reconciliador** agora chama essa função (não escreve mais nada à mão); roda de hora em hora (cron :15).
- **`bootstrap.sh`**: `AGENT_MAP` virou DINÂMICO (`load_agent_map` lê o herdr em runtime); e corrigi
  um bug latente — o `agents-flush` usava `herdr pane send` (subcomando inexistente) → nunca
  funcionou. Trocado para `herdr pane run`. Agora funciona.
- **Flush executado**: `bootstrap.sh agents-flush` enviou `/chat new` aos 8 panes (todos OK). Leitura
  do pane AGY_OPUS46 confirmou reset de contexto (a tabela com nomes velhos sai do contexto ativo).
- Integridade pós-tudo: `compliant=1, unlisted=0, agents_total=9`.
Resultado: nenhuma lista de identidade hardcoded sobrou em arquivo ativo; tudo deriva do roster vivo.

## 8e. ACHADO CRÍTICO — dispatch via herdr NÃO submete sozinho (Enter)
O operador lembrou que mensagens enviadas ao TL/agentes ficam paradas no prompt sem um Enter.
**CONFIRMADO com evidência**, e é pior/mais nuançado do que só "faltar Enter":
- **Panes Claude/AGY/Gemini**: `herdr pane run "/chat new"` executou e submeteu (novo chat iniciado). OK.
- **Panes Codex (gpt-5.5)**: o texto fica **PARADO** no input (`› /chat new`), não executa. Pior:
  - `/chat new` nem é comando do codex → "Unrecognized command '/chat'" (codex usa outro reset).
  - `send-keys Return` e `send-keys Enter` → NÃO submeteram.
  - `send-keys C-m`, `Ctrl-U`, `ctrl-u`, `C-u` → "unsupported key" (herdr usa formato `Ctrl+U`, `Escape`).
  - `send-text "\n"` → inseriu nova linha (input multiline), não submeteu.
- **Bug de detecção**: `herdr pane run` retorna exit 0 mesmo quando o codex rejeita/parqueia → o
  `agents-flush` logava "enviado com sucesso" **falsamente**. Ou seja, "injetado" no histórico do
  orquestrador pode ser FALSO para panes codex (task parada no prompt, nunca executada).
Implicação séria: o mecanismo de dispatch (orquestrador→agente via `pane run`) é **não-confiável
para codex**. Correção correta = enviar texto + tecla de submit CORRETA por tipo de CLI E **ler o
pane de volta** para confirmar que saiu do prompt (verificação por read-back), em vez de confiar no
exit code. A tecla de submit do codex via herdr ainda precisa ser determinada (Enter/Return não
funcionaram nos testes). Registrado no backlog como item de confiabilidade de dispatch.

## 8f. CORREÇÃO (fonte oficial, não palpite): customized_herdr/docs/HERDR_SOCKET_API_OFICIAL.md
Eu estava fazendo engenharia reversa do submit/Enter — mas isto JÁ está documentado. Fonte da verdade:
- `herdr pane run <pane_id> "<cmd>"` = **texto do comando + Enter** (JÁ submete).
- `herdr agent send <target> <texto>` / `pane send_text` = texto **literal, SEM Enter** (fica parado
  no prompt → precisa de Enter depois). ← corresponde exatamente à memória do operador.
- `pane send_keys` = eventos de tecla; `pane send_input`; `pane.run` via CLI.
- Robustez documentada: Socket API raw (`events.subscribe` em `pane.agent_status_changed`) +
  `herdr wait agent-status <target> --status idle|working|done|...` para confirmar execução
  (em vez de confiar no exit code do subprocess).
Conclusão corrigida: o dispatch correto é `pane run` (que já manda Enter) + verificação por
`pane read`/`wait agent-status`. O `/chat new` parado no Codex foi quirk do codex-CLI (a `/` abre o
palette e consome o Enter); reset correto do codex = `/new` (funcionou). Lição: consultar
HERDR_SOCKET_API_OFICIAL.md ANTES de testar tecla por tecla.

### Correção de tokens (doc oficial herdr 0.7.0)
`pane.send_keys`/`pane.send_input` aceitam key-combo strings **minúsculas**: `enter`, `esc`,
`ctrl+u`, `ctrl+h`, `alt+x`, `shift+tab`, `f1`, `minus`, `plus`. NÃO aceitam `Enter`/`Return`/`C-m`
(maiúsculo/estilo tmux) nem strings `prefix+`. → meus testes falharam por usar `Enter`/`Return`/`C-m`.
Primitivos corretos de dispatch:
- `herdr pane run <pane> "<cmd>"`  → texto **+ Enter** (submete). Usar para enviar comando.
- `herdr agent send <target> <txt>` / `pane.send_text` → texto **sem** Enter.
- `herdr pane send-keys <pane> enter` → tecla Enter avulsa (token minúsculo).
- `herdr wait agent-status <pane> --status done|idle|...` e `pane read --source detection` →
  verificação de execução (não confiar em exit code).
Código atualizado: `bootstrap.sh agents-flush` agora escolhe o reset por tipo (codex→`/new`,
demais→`/chat new`), usa `pane run` (texto+Enter) e faz read-back de verificação.

## 8g. MAC LOG — 2026-06-26 (verificação robusta de `agents-flush` + status de integrações)

### Contexto / decisão
Frota confirmada via `herdr pane list` (roster vivo): **100% screen-manifest**, SEM lifecycle
hooks. Apenas **três harnesses** (o modelo por trás é irrelevante p/ o Herdr — ele detecta o CLI):
- `codex` (w8:pQ/pR/pS) = OpenAI Codex CLI.
- `agy` (w8:pJ/pY) = **Antigravity = Google = Gemini** (mesma coisa; label único `agy`).
- `kiro` (w8:p12/p14/pG) = Kiro (AWS).
Labels distintos reais no roster: `['agy','codex','kiro']` (sem `gemini`/`antigravity`/`claude`).
Doc oficial (Agents + Integrations): Codex = integração só de **session identity** (estado via
screen manifest); **AGY e Kiro NÃO têm integração alguma**. NÃO existe pane Claude Code nesta
frota → `integration install claude` é N/A aqui. Logo, p/ AGY+Kiro (5 dos 8 panes) o único sinal
de estado é o screen manifest (hoje em `default_known_agent_idle_fallback`) e o único fix durável
é override de manifesto (#3) — não há `integration install` para eles.

### CHANGE — `HerdMaster/ops/bootstrap.sh`
1. **ADD** `pane_explain_state(pane, atype)` — verificação PRIMÁRIA via `herdr agent explain
   --json`. Chaves reais verificadas em herdr 0.7.0: `state` (str), `matched_rule` (obj `{id,…}`
   ou null), `fallback_reason` (str ou null). Veredito por exit code: 0=limpo, 1=suspeito,
   2=blocked. **Opção A (tolerância por tipo)**: `idle+fallback` é aceito p/ tipos sem regra de
   idle no manifesto (`agy/kiro/antigravity/gemini`); permanece SUSPECT p/ tipos com regra
   (codex perde o match `osc_title_idle` quando o palette `/` abre → cai p/ recovery).
2. **ADD** `wait_pane_settle(pane, timeout_ms)` — `herdr wait agent-status … --status idle`
   (event-driven) substitui o `sleep 2` cego no loop; mantém `sleep 1` como fallback. NOTA: p/
   agy/kiro esse idle pode ser o fallback-idle, por isso ainda confirmamos via explain depois.
3. **CHANGE** loop de `action_agents_flush`: `pane run` → `wait_pane_settle` → escada de
   verificação (explain primário ciente do tipo + read-back secundário) → recovery
   (`ctrl+u`/`esc`/re-run, tokens minúsculos) → re-verificação. "Limpo" só quando explain E
   read-back concordam.

### VERIFY (evidência, read-only — `agent explain` não envia input)
- `bash -n bootstrap.sh` → OK.
- Dry-run do veredito type-aware contra os 8 panes vivos:
  - codex (pQ/pR/pS) → `idle|osc_title_idle` → **CLEAN** (regra, estrito).
  - agy (pJ/pY) + kiro (p12/p14/pG) → `idle|default_known_agent_idle_fallback` → **CLEAN**
    (tolerado; melhor sinal disponível). Nenhum pane saudável recebe recovery desnecessário.

### MOVE / descoberta — `herdr integration status` (read-only, nada instalado por mim)
- `codex: outdated (v5 < v6)` — integração de sessão instalada porém defasada; reinstalar
  re-habilita `codex resume <id>` após restart. (Pendente go-ahead do operador.)
- `claude: not installed` — panes Claude hoje SEM restore de sessão nativa. (Pendente.)
- `opencode: outdated (v5 < v7)` — defasada (fora da frota ativa).
- `agy`/`kiro` — **ausentes da lista**: confirmam que não há integração; #3 é o único lever.

### PENDÊNCIAS (ordem)
1. (feito) #2 verificação robusta de `agents-flush`.
2. #1 config — `config.toml`: `[ui] agent_panel_sort="priority"` + `[ui.toast] delivery="terminal"`
   + `[ui.sound] enabled=true` (merge, nunca clobber; com ok do operador; `reload-config`).
3. (com go-ahead) `herdr integration install codex` (upgrade v5→v6) → restore nativo de sessão
   Codex. (Claude N/A — não há pane Claude nesta frota.)
4. #3 overrides de manifesto: `~/.config/herdr/agent-detection/{codex,agy,kiro}.toml`
   (codex: regra de blocked p/ palette; agy/kiro: regras de idle/blocked). Iterativo: captura →
   escreve regra → `agent explain --file … --json` → `server reload-agent-manifests`.
5. Instalar SKILL.md por-agente nos locais corretos da frota real (Codex→`~/.codex/AGENTS.md`;
   AGY/Antigravity e Kiro → mecanismo próprio de cada CLI, a verificar — NÃO assumir pasta
   `*/skills/` pelo nome). Com confirmação por-local. Coordenação read-side apenas.

## 8h. MAC LOG — 2026-06-26 (research AGY + verificação live: versão, manifests, schema Q1)

### CONTEXT
Time de pesquisa (AGY) entregou relatório vendor-sourced; cruzado com comandos live nesta máquina.
Regra: output live vence doc. Brief de pesquisa atualizado com seção "RESOLUTION ADDENDUM"
(`AOP/docs/RESEARCH_BRIEF_HERDR_OPEN_QUESTIONS_2026-06-26.md`).

### VERIFY (live, read-only)
- `herdr --version` → **0.7.1** (não 0.7.0; o "0.7.0" vinha das cópias de doc no repo, não do binário).
- `herdr server --help` → confirmam-se 3 comandos ausentes do CLI Reference público:
  `agent-manifests`, `update-agent-manifests`, `reload-agent-manifests`.
- `herdr server agent-manifests --json` → todos `result: current`. agy=2026.06.24.1 (o MAIS novo),
  kiro=2026.06.10.1, gemini=2026.06.10.1 (SEPARADO de agy), codex=2026.06.10.3. → nada a atualizar
  via remote; #3 (override local) é genuinamente necessário.
- Capturado `~/.local/state/herdr/agent-detection/remote/agy.toml` (760 bytes) = SCHEMA real do Q1.

### FINDING-chave (root cause AGY fallback-idle, provado)
`agy.toml` só tem regras de `blocked` + `working`; **não tem regra de `idle`**. Logo prompt pronto
→ nada casa → `default_known_agent_idle_fallback`. É design upstream. Fix = override local com
ruleset completo existente + nova regra `idle` (overrides REPLACE, não merge — confirmado).

### Q-status final (resumo): Q1 resolvido via captura on-disk; Q2/Q3/Q5/Q7/Q8/Q10/Q12 resolvidos;
Q4/Q6/Q9 precisam de teste live; remote-patch claim segue UNVERIFIED (não load-bearing).

### NEXT (ordem atualizada)
#3 overrides (top, de-riscado): capturar `--source detection` por agente → escrever agy.toml/
kiro.toml (ruleset completo + idle) → `reload-agent-manifests` → re-verificar via `agent explain`.
Depois #1 config; #6 codex upgrade (go-ahead); SKILL.md por-harness.

## 8i. MAC LOG — 2026-06-26 (#3 IMPLEMENTADO: overrides de manifesto agy/kiro/codex)

### RESULTADO (headline)
Os 8 panes da frota agora reportam `idle` por REGRA QUE DEU MATCH — ZERO
`default_known_agent_idle_fallback`. Antes: 5/8 (agy+kiro) eram fallback; codex era frágil
(só OSC title).
- agy (w8:pJ, w8:pY) + kiro (w8:p12, w8:p14, w8:pG) → idle | **ready_prompt_idle**
- codex (w8:pQ, w8:pR, w8:pS) → idle | **live_idle**

### ADD — 6 arquivos
- Staging (versionado no repo): `HerdMaster/ops/herdr-overrides/staging/{agy,kiro,codex}.toml`
- Instalado (config do usuário): `~/.config/herdr/agent-detection/{agy,kiro,codex}.toml`
Cada um = ruleset completo do manifesto remoto (verbatim) + 1 regra idle nova @priority 50
(menor que todas existentes → working/blocked sempre vencem). REPLACE semantics confirmado live.

### Regras idle adicionadas (assinaturas capturadas live via `pane read --source detection`)
- agy `ready_prompt_idle`: contains ["? for shortcuts"] (agy NÃO usa osc_title).
- kiro `ready_prompt_idle`: contains ["ask a question or describe a task"].
- codex `live_idle`: line_regex ['gpt-[0-9.]+\s+\w+\s+·\s+/'] (footer modelo·cwd), com not-guards
  de blocker. Motivo: osc_title_idle do codex só casa com OSC title, observado VAZIO em startup
  (w8:pQ) E in-session (w8:pR) → fallback. live_idle (whole_recent) cobre isso.

### SCHEMA GOTCHA (descoberto só no load do Herdr, tomllib NÃO pega)
`version` TEM que ser dotted-numeric. `2026.06.24.1-local.1` foi REJEITADO ("version must be
dotted numeric"), override ignorado, remote permaneceu ativo (fail-safe). Fix: `.99` no último
segmento. Validar SEMPRE pelo output do reload (`source_kind: "local override"`, sem `warning`).

### BONUS (prova do /chat-new): buffer de w8:pR mostrou "Unrecognized command '/chat'. Type / for
a list" ×3 → codex rejeita /chat new, exige /new. Confirma `reset_cmd_for_type` do bootstrap.sh.

### VERIFY: `herdr agent explain <pane> --json` nos 8 panes → todos matched_rule + fallback=None.
Doc completa: RESEARCH_BRIEF "IMPLEMENTATION ADDENDUM".

### ROLLBACK: `rm ~/.config/herdr/agent-detection/<agent>.toml && herdr server reload-agent-manifests`.

### RESIDUAL: (a) regra palette→blocked do codex DIFERIDA (não houve estado preso pra capturar);
(b) not-guards/idle verificados só contra buffers IDLE — re-verificar contra tela WORKING quando
houver agente em execução; (c) override agy SOMBREIA remote ativamente atualizado upstream —
diffar periodicamente o base staged vs remote e re-merge.

## 8j. MAC LOG — 2026-06-27 (testes live end-to-end com dados reais; 2 bugs achados+corrigidos)

### CONTEXT
5 testes live contra a frota real (codex pQ/pR/pS, agy pJ/pY, kiro p12/p14/pG). Prompts e resets
REAIS enviados; `agent explain` é read-only. Doc completa: RESEARCH_BRIEF "LIVE TEST REPORT".

### T1 ✅ — transição WORKING real (kiro w8:pG): idle→working(kiro_working_marker)→idle(ready_prompt_idle);
resposta "391" no buffer (execução real). PROVA empírica: regra working(prio100) vence nossa idle
(prio50); idle NÃO dispara falso durante trabalho. (Design antes era só teórico.)

### T2 — `wait agent-status`: exit codes CONFIRMADOS (0=match, 1=timeout). MAS achado crítico:
`wait --status idle` é NÃO-confiável p/ agentes screen-manifest (deu timeout até sobre transição
working→idle comprovada). `agent explain` (poll) rastreia estado com precisão/instantâneo.

### T3 ✅ (após corrigir 2 bugs) — `bootstrap.sh agents-flush` live:
- CHANGE bootstrap.sh BUG1: `wait_pane_settle` trocado de `wait agent-status idle` (queimava 8s)
  para POLL de `agent explain` (retorna 0 em 0.03s em pane idle).
- CHANGE bootstrap.sh BUG2: loop de verificação gateava em `explain rc=0 AND pane_reset_landed`;
  o eco do comando/ack pós-reset deixava o read-back falso → pane LIMPO virava "suspeito"→recovery.
  FIX: `agent explain` é autoridade ÚNICA; read-back vira log informativo; +branch rc=2→BLOCKED.
- LIVE: resets reais nos 8 panes; todos `limpo` via explain, ZERO falso-suspeito, ZERO recovery
  desnecessária. codex usa /new, agy/kiro /chat new. Pós-flush 8/8 idle+rule-matched.
  (codex volta a casar osc_title_idle prio100 quando /new repopula o título → vence live_idle prio50;
  design em camadas funcionando.)

### T4 ✅ — upgrade integração codex v5→v6: `herdr integration install codex` (in-place idempotente,
toca ~/.codex/{herdr-agent-state.sh,hooks.json,config.toml}) → `codex: current (v6)`. Dá restore de
SESSÃO (codex resume <id>), NÃO autoridade de estado. Rollback: integration uninstall codex.

### T5 ✅ — config WSL: notify-send AUSENTE → delivery="system" falharia; delivery="terminal" é o
caminho WSL correto. config.toml JÁ tinha agent_panel_sort="priority" + delivery="terminal";
reload-config → applied, 0 diagnostics. FLAG: pane_history=true grava conteúdo de panes (possíveis
segredos) em ~/.config/herdr/session-history.json (~900KB) — fora do repo (sem exposição git);
setting deliberado do operador, mantido.

### NET CODE: HerdMaster/ops/bootstrap.sh (wait_pane_settle + loop de verificação do agents-flush);
bash -n OK; exercido live nos 8 panes.

## 8k. MAC LOG — 2026-06-27 (SKILL.md instalado por-harness; Q10)

### ADD — cópia canônica + 3 instalações
- Canônica (repo): `HerdMaster/ops/herdr-overrides/SKILL.md` (fetch live do GitHub raw, 8988b;
  +2 notas locais → 9605b: formato de id `w8:pX`, e o achado de `wait agent-status idle` não-confiável).
- Instalado em: `~/.codex/skills/herdr/SKILL.md`, `~/.gemini/skills/herdr/SKILL.md`,
  `~/.kiro/skills/herdr/SKILL.md` (9605b cada).

### DECISÃO (inspeção, não suposição): os 3 harnesses usam a MESMA convenção, comprovada pelos
skills `openspec-*` já presentes em disco: `~/.<harness>/skills/<nome>/SKILL.md` (uma pasta por
skill). Seguimos a convenção REAL em disco em vez do hint genérico do agent-guide (que sugeria
`~/.codex/AGENTS.md` p/ codex). Nenhum dir `herdr` pré-existente → ZERO clobber.

### VERIFY: frontmatter `name: herdr` intacto nos 3; guardrail `HERDR_ENV=1` presente nos 3; herdr
aparece ao lado dos openspec-* skills.

### NOTA guardrail (Q10): `HERDR_ENV=1` é gate de PROMPT, não enforcement. HerdMaster segue sendo a
autoridade de dispatch/reset; o skill só habilita coordenação read-side (pane read, wait, pane list).
ROLLBACK: `rm -rf ~/.<h>/skills/herdr`.

## 8l. MAC LOG — 2026-06-27 (plano-mestre PROD p/ TL + anexo Herdr Ops)

### CONTEXT
A pedido do operador: consolidar TODO o planejamento pendente da AOP num plano-mestre PROD para o
TL (KIRO_OPUS-48) gerir, + anexo de suporte operacional Herdr. Regra: tudo ancorado em fonte, zero
fabricação; respeitar GSD (sem bypass do phase loop).

### READ (fontes ancoradas)
PRD-003, PRD-004, AOP/.planning/{PROJECT,ROADMAP,STATUS,TECH_DEBT_BACKLOG,TL_HANDOFF,
FINAL_STATUS_REPORT_TL,OPENSPEC_RECONCILIATION}.md, openspec/changes/agnostic-orchestration-platform/
{tasks,design}.md, agent-route-dashboards-provisioning/tasks.md.

### ADD — 2 docs
- `AOP/.planning/MASTER_DELIVERY_PLAN_TL.md` (10.5KB): baseline TL-verificado, inventário completo
  (F0-F7; 14 tasks OpenSpec abertas; TD7/8/9/10/12/13/14; change dashboards 0/25; backlog diferido),
  4 ondas A-D c/ donos/ETA, gates GSD, critério "100%", papéis, rastreabilidade de fontes.
- `AOP/.planning/HERDR_OPS_SUPPORT_ANNEX_TL.md` (9.4KB): base operacional Herdr testada live —
  autoridade de estado, schema de manifesto+overrides (entregues), dispatch (pane run/reset por
  harness), achado crítico de waits (wait-idle não-confiável → poll explain), agents-flush, WSL,
  integração codex v6. Mapeia explicitamente p/ tasks 3.2/3.3 e operação das ondas.

### VERIFY (live, read-only)
- `openspec list` confirma: agnostic-orchestration 51/65, dashboards 0/25, agnostic-ai 0/54,
  live-integration 9/9 — bate exatamente com o plano.
- 3 overrides instalados + staging masters presentes; issues-view.tsx (alvo TD13) existe.
- Corrigido path no anexo: masters ficam em `herdr-overrides/staging/` (não na raiz do dir).

### NOTA: nenhum código de produto AOP foi alterado — esta entrega é planejamento/handoff.
TL agora tem plano único acionável + base operacional Herdr p/ tocar as ondas e o deploy da próxima fase.

## 9. Lições / princípios reforçados
- Verificar a fundação antes de empilhar trabalho economiza horas.
- "Vazio" pode ser sintoma, não saúde.
- Backup é pré-condição de qualquer ação destrutiva — nunca o contrário.
- Hardcode de identidade (whitelist `w6`) é dívida que vira auto-sabotagem; a cura é fonte única
  derivada da realidade + reconciliação periódica.
- Backlog (`AOP/docs/BACKLOG_GRAFANA.md`) captura o que ficou (métricas No data, FinOps/tracing,
  acesso estável ao Grafana, hardening).

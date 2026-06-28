# Herdr Socket API — DOCUMENTAÇÃO OFICIAL (fonte da verdade)

> Fornecida pelo stakeholder. ESTA é a API real do Herdr 0.7.0. Toda integração (adapter/parser)
> DEVE ser construída contra este documento — NÃO contra suposições nem contra RESEARCH_Herdr_Capabilities.md
> (que estava divergente). Em caso de conflito, ESTE arquivo prevalece.

## Transporte
- **Newline-delimited JSON sobre Unix domain socket.** Um request por linha; resposta inclui o mesmo `id`.
- Socket: `~/.config/herdr/herdr.sock` (ou `~/.config/herdr/sessions/<name>/herdr.sock`).
- Resolução: `--session` > `HERDR_SOCKET_PATH` > `HERDR_SESSION` > default.
- Subscriptions de evento mantêm a conexão aberta após o ack inicial.
- `ping` → `{"result":{"type":"pong"}}`. Erro → `{"error":{"code":...,"message":...}}`.

## Métodos raw (dot notation) — o que importa para o HerdMaster
- **Agent:** `agent.list`, `agent.get`, `agent.read`, `agent.send`, `agent.rename`, `agent.focus`, `agent.start`, `agent.explain`
- **Pane:** `pane.list`, `pane.get`, `pane.read`, `pane.send_text`, `pane.send_keys`, `pane.send_input`, `pane.run` (via CLI), `pane.report_agent`, `pane.wait_for_output`, `pane.split`, `pane.close`
- **Events:** `events.subscribe`, `events.wait`
- **Workspace:** `workspace.list/create/get/focus/rename/close`
- **Server:** `ping`, `server.stop`, `server.reload_config`

## Wrappers CLI equivalentes (o que o adapter por subprocess deve chamar)
| Ação | CLI REAL | Observação |
|------|----------|-----------|
| Listar agentes | `herdr agent list` | retorna JSON `{"result":{"type":"agent_list","agents":[...]}}` — SEM `--json` |
| Ler pane/agente | `herdr pane read <pane_id> --source visible\|recent\|recent-unwrapped --lines N` ou `herdr agent read <target>` | |
| Enviar TEXTO ao agente | `herdr agent send <target> <text>` | escreve texto literal |
| Enviar comando+Enter | `herdr pane run <pane_id> "<cmd>"` | texto do comando + Enter |
| Esperar estado | `herdr wait agent-status <target> --status idle\|working\|blocked\|done\|unknown` | semântico; status, não "state" |
| Listar panes | `herdr pane list [--workspace <id>]` | |
| Listar workspaces | `herdr workspace list` | |

## Formato real de `agent.list` (envelope + campos)
```json
{"id":"...","result":{"type":"agent_list","agents":[
  {"agent":"agy","agent_status":"idle","pane_id":"w4:p2","workspace_id":"w4","tab_id":"w4:t1","terminal_id":"term_...","cwd":"...","foreground_cwd":"...","focused":false},
  {"agent":"codex","agent_status":"idle","pane_id":"w4:pA","workspace_id":"w4","agent_session":{"source":"herdr:codex","agent":"codex","kind":"id","value":"..."}, ...}
]}}
```
- Identidade: usar **`pane_id`** como id estável (nomes `agent` podem repetir — há 2 "codex").
- Estado: **`agent_status`** ∈ {idle, working, blocked, unknown, done}.
- `agent_session` aparece quando há sessão nativa; tolerar ausência.

## Eventos para o WATCHDOG (camada primária, FR-301) — usar Socket API, não polling
`events.subscribe` com, p.ex.:
```json
{"id":"sub_1","method":"events.subscribe","params":{"subscriptions":[
  {"type":"pane.agent_status_changed","pane_id":"w4:pA"}
]}}
```
Eventos disponíveis: `pane.agent_status_changed`, `pane.created/closed/focused/moved/exited`,
`pane.agent_detected`, `pane.output_matched`, `workspace.*`, `worktree.*`.
→ O watchdog deve **assinar** `pane.agent_status_changed` em vez de só fazer polling por CLI.

## Reportar estado de agente (se o HerdMaster precisar marcar estado)
`pane.report_agent` (semântico) / `pane.report_agent_session` / `pane.report_metadata` (visual).

## Acoplamento via PLUGIN (ADR-001 / FR-AC-01)
Plugin = pacote com `herdr-plugin.toml` (manifest declara actions, **event hooks**, panes, link handlers).
`min_herdr_version` obrigatório. Instala via `herdr plugin install` / `plugin.link`. Hooks de evento
rodam quando o Herdr emite o evento (ex.: boot/workspace.created) → caminho oficial para subir o
HerdMaster junto com o Herdr.

## Decisão arquitetural (Tech Lead)
O adapter DEVE migrar para o **Socket API raw** (request/response + subscriptions) por dois motivos
do PRD: (1) watchdog primário por eventos em tempo real (FR-301), (2) robustez vs. spawnar subprocess
por chamada. CLI wrappers ficam como fallback secundário (FR-302/§12).

## Formatos de resposta capturados ao vivo (referência p/ o Codex)
- `agent.list` → `{"result":{"type":"agent_list","agents":[{agent,agent_status,pane_id,workspace_id,...}]}}`
- `pane.read`  → `{"result":{"type":"pane_read","read":<conteúdo>}}`
- `pane.list`  → `{"result":{"type":"pane_list","panes":[...]}}`
- `agent.explain` → `{"result":{"type":"agent_explain","explain":{...}}}`
Todos via socket ~/.config/herdr/herdr.sock (newline-JSON, mesmo id). Erros: {"error":{"code","message"}}.

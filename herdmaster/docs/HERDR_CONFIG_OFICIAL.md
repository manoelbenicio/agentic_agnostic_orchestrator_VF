# Herdr Configuration — OFICIAL (só o que importa ao HerdMaster)

> Fonte: doc oficial do stakeholder. A maioria das opções (tema, keybindings, som, scrollback) NÃO
> afeta o HerdMaster. Abaixo, apenas o que a integração precisa.

## Config do Herdr
- Arquivo: `~/.config/herdr/config.toml`. `herdr --default-config` imprime o default completo.
- Aplicar mudanças no servidor rodando: **`herdr server reload-config`** (ou método `server.reload_config`).
- Valor inválido → Herdr usa default seguro + aviso no startup.

## Variáveis de ambiente que o HerdMaster DEVE respeitar (ordem de resolução do socket)
| Var | Uso |
|-----|-----|
| `HERDR_SOCKET_PATH` | override do caminho do socket (low-level) — o adapter deve checar isto ANTES do default |
| `HERDR_SESSION` | seleciona sessão nomeada (socket em ~/.config/herdr/sessions/<name>/herdr.sock) |
| `HERDR_CONFIG_PATH` | override do config do Herdr |
| `HERDR_LOG` | filtro de log (ex.: `herdr=debug`) |

→ Resolução do socket pelo adapter (HM-FIX-05): `HERDR_SOCKET_PATH` > `HERDR_SESSION` > default
  `~/.config/herdr/herdr.sock`. (Igual ao que a doc do Socket API já dizia.)

## Logs do Herdr (para DEBUG da integração)
- `~/.config/herdr/herdr-server.log` ← principal para diagnosticar socket/estado de agente
- `~/.config/herdr/herdr-client.log`
- `~/.config/herdr/herdr.log`
- Rotacionam automaticamente.

## Restart/reload (relevante para o ADR-001 / acoplamento)
- `herdr server reload-config` aplica a maioria das mudanças sem reiniciar panes.
- `herdr server stop` para o servidor.
- Agent session restore: `[session] resume_agents_on_restore = true` (default) — Herdr restaura panes
  de agentes após restart do servidor. Relevante para a resiliência do acoplamento.

## NÃO relevante ao HerdMaster (ignorar): tema, keybindings, sidebar/UI, toast/som, scrollback,
## worktrees UI, IME, nested launches, kitty graphics.

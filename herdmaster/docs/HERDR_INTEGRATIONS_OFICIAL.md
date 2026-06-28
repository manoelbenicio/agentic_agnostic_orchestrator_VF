# Herdr Integrations & Modelo de Autoridade de Estado — OFICIAL + estado real

> Fonte: documentação oficial do stakeholder. Complementa docs/HERDR_SOCKET_API_OFICIAL.md.
> Define COMO o estado dos agentes é autorado — crítico para o WATCHDOG do HerdMaster.

## Dois tipos de integração (modelo de autoridade)

| Tipo | Agentes | Efeito no estado |
|------|---------|------------------|
| **Lifecycle authority** | Pi, OMP, Kimi, **OpenCode**, **Kilo**, Hermes | Hook/plugin AUTORA idle/working/blocked. Herdr NÃO usa screen-manifest fallback p/ esse pane. |
| **Session identity** | Claude, **Codex**, Copilot, Devin, Droid, Qoder, Cursor | Integração reporta sessão p/ restore. Estado vem do **screen-manifest detection** do Herdr. |

→ Em ambos os casos, o **estado semântico final está SEMPRE disponível via `agent.list`/`agent_status`
   e via eventos `pane.agent_status_changed`**. O HerdMaster NÃO precisa saber qual tipo de integração
   cada agente usa — ele consome `agent_status` do Herdr, que já consolida a autoridade correta.

## ESTADO REAL DO AMBIENTE (herdr integration status — ao vivo 2026-06-22)

| Agente | Integração | Versão | Tipo | Implicação |
|--------|-----------|--------|------|------------|
| codex | instalada | v5 (current) | session identity | estado via screen detection do Herdr |
| opencode | instalada | v5 (current) | **lifecycle authority** | reporta idle/working/blocked direto |
| kilo | instalada | v1 (current) | lifecycle authority | reporta lifecycle direto |
| pi/omp/claude/copilot/devin/droid/kimi/hermes/qodercli/cursor | NÃO instaladas | — | — | — |

> Os 4 agentes vivos no workspace w4 (agy, codex, opencode, codex) têm seu `agent_status` resolvido
> pelo Herdr (codex via screen-detection; opencode via lifecycle hook). O HerdMaster lê tudo igual
> via `agent.list` / eventos.

## Implicação ARQUITETURAL para o WATCHDOG (HM-008)

A documentação confirma a decisão do INC-005:
1. **Camada PRIMÁRIA = eventos do Socket API** (`events.subscribe` → `pane.agent_status_changed`).
   O Herdr já entrega o estado semântico autoritativo (vindo de hook OU screen-detection). O watchdog
   NÃO deve reimplementar detecção de tela — só CONSUMIR `agent_status`.
2. **Camada SECUNDÁRIA = polling `agent.list`** (fallback se o stream cair).
3. **Camada TERCIÁRIA = `pane.read` + hash** (terminal congelado) — só como último recurso, e
   redundante para agentes com lifecycle authority (opencode/kilo).

## Comandos úteis de DEBUG de integração
- `herdr integration status` — versões instaladas (usado acima).
- `herdr agent list` — agentes conhecidos + agent_status.
- `herdr pane read <id> --source recent --lines 50` — verificar o que o Herdr vê no pane.
- `herdr agent explain <target> [--json]` / método `agent.explain` — porque o Herdr classificou aquele
  estado (regra de manifest, evidência, skip reason). ÓTIMO para debugar estado errado.

## Reporte de estado custom (se o HerdMaster precisar)
`herdr pane report-agent <id> --source custom:... --agent X --state working --custom-status "..."`
(semântico) ou `pane report-metadata` (visual). O HerdMaster v1 NÃO precisa reportar — ele só consome.

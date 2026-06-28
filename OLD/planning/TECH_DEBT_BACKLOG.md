# TECH DEBT BACKLOG — AOP (fonte ÚNICA, com ETA) — zerar tudo
**v1.0 · 2026-06-26 · Kiro (Principal Architect).** Regra: agentes 24x7, acabou um → manda outro, até ZERAR.
Status: ⬜ não atribuído · 🟡 em execução · ✅ feito (check-out+PRINT+SHA). ETA = wall-clock estimado por task.

| ID | Débito técnico | Prioridade | ETA | Dono | Status | Fonte |
|----|----------------|-----------|-----|------|--------|-------|
| TD4 | Robustez DB/pool: `rollback` em erro + `pool check=ConnectionPool.check_connection` + `reconnect_failed` (psycopg) — NÃO está no código ainda | **P0** | 45m | CODEX_55#0 | 🟡 | RISK R1/R2 |
| TD6 | Coupling control-plane↔HerdMaster DEGRADED (`HerdMaster HTTP unavailable`, message bus down) | **P0** | 30m | ⬜ a atribuir | ⬜ | /health |
| TD1 | `inbox_api` backend + plugar UI `/inbox` (hoje placeholder "Simulando fetch") | **P1** | 30m | CODEX_55#1 | 🟡 | EMPTY_SCREENS |
| TD2 | `/api/issues/my` backend + plugar `/my-issues` (placeholder) | **P1** | 30m | CODEX_55#3 | 🟡 | EMPTY_SCREENS |
| TD3 | `settings_api` backend + plugar `/settings` (placeholder) | **P1** | 30m | CODEX_55#2 | 🟡 | EMPTY_SCREENS |
| TD5 | OTTL: trilha de tasks no Postgres + reconciliador + board %/ETA + **implementar rota `herdmaster tasks`** (hoje "unsupported tasks route") | **P1** | 120m | AGY_Gemini-PRO31 | 🟡 | RISK R7 / REQUEST_OTTL |
| TD8 | Reconciliar OpenSpec ↔ realidade (change está **2/65 tasks** vs código feito) | **P1** | 60m | ⬜ a atribuir | ⬜ | REMEDIATION G1 |
| TD11| `squad_api` backend (topologia do squad-builder; Canvas existe sem backend) | **P2** | 45m | ⬜ a atribuir | ⬜ | REMEDIATION G3 |
| TD7 | Grafana: publicar porta `3000:3000` no docker-compose + expandir dashboards por agente/rota | **P2** | 30m | ⬜ a atribuir | ⬜ | Grafana check / R9 |
| TD9 | Integração F1→F6 (app-shell ligando rotas, dados reais ponta-a-ponta, zero mock) | **P2** | 60m | ⬜ a atribuir | ⬜ | REMEDIATION R4 |
| TD10| QA E2E exaustivo (F7) — **só no FINAL**, após TD1–TD9 | **P3** | fim | ⬜ rotativo | ⬜ | regra |

## Caminho crítico
P0 (TD4, TD6) em paralelo → P1 (TD1,2,3,5,8) → P2 (TD11,7,9) → P3 (TD10 QA final). Workers ociosos puxam o próximo ⬜.

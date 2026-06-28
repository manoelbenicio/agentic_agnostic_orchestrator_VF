# SPEC — FASE 4 · Seats + Sessions/OAuth (device-login dos CLIs)
**Dono:** AG-4 · **Status:** ready (backend pode iniciar já) · **Depende de:** F0

## Discuss
Seat pool hoje é hardcoded; não há UI de provisionamento nem tela de Sessions/OAuth dos CLIs.

## WHAT
- Backend: endpoints de provisionamento de seats (register/update/remove) — **remover o seat hardcoded**;
  device-login por vendor (Codex/Claude/Gemini/Kiro) + status de sessão; isolamento por seat (HOME/config-dir).
- UI Seats: registrar/editar/remover; estado lease/available real; afinidade.
- UI Sessions: iniciar device-login (mostra código + URL), status (connected/pending/expired), renovar/revogar.

## Escopo de paths
`AOP/web/src/app/{seats,sessions}/**`, `components/{seats,sessions}/**`, `AOP/control-plane/{seats_api,sessions_api}/**`, rotas em `app/main.py`.

## Aceite (UAT)
- [ ] Seats vêm de fonte real (vazio se não configurado — nunca seat fake); registrar/remover funciona.
- [ ] Device-login por vendor funcional; multi-sessão sem colisão.
- [ ] pytest + build verdes. **Print** em `AOP/.planning/evidence/AG-4-seats-sessions.png`.

## Evidência obrigatória
pytest + build + curls + PRINT real no ledger raiz.

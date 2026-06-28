# 📨 DISPATCH ONDA 1 — PARA O TL/ORQUESTRADOR (CC: operador)
De: Kiro (planejador) · Assunto: Executar Onda 1 (Fase 0 + backends F1/F4)

TL, execute AGORA, em paralelo. Leia também: AOP/.planning/TL_BRIEFING.md e AOP/.planning/phases/phase-0-design-system/PLAN.md.

GOVERNANÇA (recuse check-out que violar):
- Cada agente faz CHECK-IN antes de iniciar e CHECK-OUT ao terminar no arquivo raiz
  /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/CHECKIN_OUT_GSD.md
  com timestamp UTC + nome do agente + PRINT real salvo em AOP/.planning/evidence/<AGENTE>-<task>.png.
- Sem print/evidência = task inválida (reabrir).
- Design system: SOMENTE HEX Indra (sem OKLCH). ZERO mock/placeholder em produção. Paths isolados por agente.

INJETAR (paralelo):
1) PANE AG-1 → prompt "PANE AG-1" do TL_BRIEFING.md — Design System Indra HEX + Shell (menu lateral esquerdo + micro-interações). Escopo: AOP/web/src/components/ui, app-shell.tsx, page-kit.tsx, lib/theme.
2) PANE AG-2 (backend primeiro) → prompt "PANE AG-2" — tabela `projects` + endpoints CRUD /projects + rotas em app/main.py. Escopo: AOP/control-plane/projects_api, AOP/web/src/app/projects.
3) PANE AG-4 (backend primeiro) → prompt "PANE AG-4" — seats_api + sessions_api (remover seat hardcoded; device-login por vendor). Escopo: AOP/control-plane/{seats_api,sessions_api}, AOP/web/src/app/{seats,sessions}.

AO CONCLUIR cada agente (CHECK-OUT COMPLETED com print): atualize AOP/.planning/STATUS.md (célula → ✅) e reporte ao Kiro (planejador) via operador. Reinjete qualquer pane sem progresso > 5 min.
Quando AG-1(shell) + os 2 backends fecharem, o Kiro libera a ONDA 2 (AG-2 UI, AG-3, AG-5, AG-6).

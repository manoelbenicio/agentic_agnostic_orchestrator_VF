# PLAN — FASE 0 · Design System Indra (HEX) + Shell
**Executado por:** Kiro · **Etapa GSD:** Plan · **Dono da execução:** AG-1 (via TL)

## Tarefas (ordem)
1. **Tokens (verificar):** confirmar `globals.css` com tokens Indra HEX (feito) — light/dark, status, sidebar.
2. **Primitivos UI** (`AOP/web/src/components/ui/`): Button (primary/secondary/ghost/destructive), Input, Select,
   Dialog, Dropdown, Tabs, Table, Card, Badge/Tag, Toast, Tooltip, Skeleton, EmptyState, Avatar, Resizable — via shadcn + tokens.
3. **Shell** (`app-shell.tsx`): menu lateral agrupado (Visão geral/Construir/Operar/Workspace), ativo c/ barra accent,
   colapsável; header (busca Ctrl+K, tema, status coupling, avatar); container max-w consistente.
4. **Efeitos:** micro-interações sutis (fade/float/wipe), foco visível, transições de tema sem flash.
5. **page-kit** (PageHeader/EmptyState) padronizado para as telas reutilizarem.
6. **Verify build:** `npm run build` verde + dev server; **print** da home (shell) em `AOP/.planning/evidence/AG-1-shell.png`.

## Escopo de paths (isolado)
`AOP/web/src/components/ui/**`, `app-shell.tsx`, `page-kit.tsx`, `lib/theme*`, `app/globals.css` (já feito).

## Critério de conclusão (Execute)
- Componentes só com tokens HEX (zero cor fora dos tokens, zero OKLCH); shell responsivo light/dark;
  build verde; **PRINT real** anexado; CHECK-IN/CHECK-OUT no ledger raiz com timestamp + nome do agente.

## Distribuível para o TL
→ Injetar no pane AG-1 o prompt da seção "PANE AG-1" do `TL_BRIEFING.md`, complementado por este PLAN.
   Etapas seguintes (Verify/Ship) após Execute: `gsd-verify-work` + `gsd-ui-review` (6 pilares) → `gsd-ship`.

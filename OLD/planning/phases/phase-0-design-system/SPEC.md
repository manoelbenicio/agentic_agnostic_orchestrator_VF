# SPEC — FASE 0 · Design System Indra (HEX) + Shell premium
**Dono:** AG-1 · **Status:** ready · **Depende de:** —

## Discuss (contexto)
Base visual de toda a aplicação. Tokens HEX Indra já aplicados em globals.css. Falta a biblioteca
de componentes e o shell (menu lateral esquerdo + header) com micro-interações premium.

## WHAT (entregáveis)
- Biblioteca de componentes em HEX Indra: Button (primary/secondary/ghost/destructive), Input, Select,
  Dialog/Modal, Dropdown, Tabs, Table, Card, Badge/Tag, Toast, Tooltip, Skeleton, EmptyState, Avatar, Resizable.
- **Menu lateral esquerdo** agrupado (Visão geral / Construir / Operar / Workspace) com estado ativo
  (barra accent cyan), colapsável; header com busca (Ctrl+K), toggle tema (light/dark/system), status API/coupling, avatar.
- Micro-interações sutis (fade/float/wipe "invisíveis"), foco visível, scrollbars refinadas.

## Escopo de paths
`AOP/web/src/components/ui/**`, `app-shell.tsx`, `page-kit.tsx`, `lib/theme*`. NÃO tocar telas.

## Out of scope
Telas de domínio (Projects/Issues/etc.) — são outras fases.

## Aceite (UAT)
- [ ] Todos os componentes usam tokens HEX (nenhuma cor fora dos tokens; sem OKLCH).
- [ ] Shell responsivo e alinhado, menu lateral com ativo/hover corretos, light/dark.
- [ ] `npm run build` verde. **Print** da home com o shell salvo em `AOP/.planning/evidence/AG-1-shell.png`.

## Evidência obrigatória
Saída do build + PRINT real no ledger raiz (CHECK-IN antes / CHECK-OUT depois, timestamp + nome).

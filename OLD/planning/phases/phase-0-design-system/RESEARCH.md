# RESEARCH — FASE 0 · Design System Indra (HEX) + Shell
**Executado por:** Kiro (planejamento) · **Etapa GSD:** Research

## Achados técnicos
- **Tokens HEX no Tailwind v4:** `@theme inline` aceita valores HEX direto; já convertido em `globals.css`
  (sem OKLCH). Variáveis CSS por tema (`:root` / `.dark`) mantêm nomes semânticos → componentes não quebram.
- **Componentes:** shadcn/ui (Radix) como base (acessível); estilizar via tokens Indra. Ref de qualidade:
  skills `shadcn`, `tailwindcss-advanced-layouts`, `senior-uiux-data-products`, `fortune500-executive-dashboard`.
- **Menu lateral:** padrão sidebar agrupada (Visão geral/Construir/Operar/Workspace) + barra accent cyan no ativo;
  validado nos 5 mockups (`AOP/docs/mockups/`). Layout 1 (sidebar clássica) é o mais escalável p/ muitas telas.
- **Micro-interações:** CSS/`framer-motion` leves (fade/float/wipe), princípio "invisible animation"
  (de `slide-animation-director`, portado p/ web). Sem efeitos infantis.
- **Contraste/A11y:** paleta Indra — ink `#00475A` sobre off-white `#F2F5F6` e cyan `#00B0BD` como accent
  passam contraste AA para texto/realce; validar foco visível (já no globals).
- **Dark mode:** deep `#002B3A`/dark `#003E50` como bg; cyan como primary p/ contraste.

## Riscos
- Over-animação (perf/distrátil) → limitar a entradas sutis e estados.
- Divergência de cor → proibido cor fora dos tokens (lint/review).

## Decisões de research
- Base de layout: **sidebar clássica (Layout 1)** + cards KPI no estilo bento (Layout 5) para dashboards.
- Stack: Next.js + Tailwind v4 + shadcn/ui + tokens Indra HEX. Animações: CSS-first + framer-motion onde necessário.

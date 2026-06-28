# DISCUSS — FASE 0 · Design System Indra (HEX) + Shell
**Executado por:** Kiro · **Etapa GSD:** Discuss · **Ambiguity score:** baixo (1 decisão registrada)

## Requisitos clarificados
- Design system **HEX Indra obrigatório** (sem OKLCH). Cores só via tokens.
- **Menu lateral esquerdo** agrupado, colapsável, com ativo destacado (barra accent).
- Header: busca (Ctrl+K), toggle tema (light/dark/system), status API/coupling, avatar/usuário.
- Biblioteca de componentes acessível (Radix/shadcn) estilizada nos tokens; light/dark.
- Micro-interações premium sutis; experiência nível Fortune 500.

## Decisão registrada (assunção de trabalho — sobreescrevível pelo stakeholder)
- **Layout base = sidebar clássica (mockup 01)** para o shell + **cards KPI estilo bento (mockup 05)** nos dashboards.
  Justificativa: sidebar escala melhor para ~13 telas; bento eleva o "wow" executivo nos KPIs.
  → Se o stakeholder preferir outro dos 5 mockups, troca-se o shell sem afetar os tokens.

## Fora de escopo da F0
Telas de domínio (Projects/Issues/Seats/etc.) — fases seguintes consomem o design system.

## Critérios de aceite (UAT) confirmados
- Todos os componentes usam tokens HEX; shell alinhado/responsivo; light/dark ok; `npm run build` verde; **print** anexado.

## Pergunta aberta (não bloqueante)
- Confirmar o layout base (01 sidebar) ou indicar outro dos 5 mockups. Default assumido: 01 + KPIs estilo 05.

# SPEC — FASE 6 · Settings + Inbox + My Issues + Search + polish
**Dono:** AG-6 · **Status:** ready · **Depende de:** F0

## WHAT
- Settings (10 abas): General, Members (convite/roles), Repositories, GitHub, Integrations, Profile,
  Preferences (tema/idioma/timezone), Notifications, API Tokens (criar/revogar/reveal único), Labs.
- Inbox: tipos de evento com ícones, read/unread, bulk archive, painel redimensionável.
- My Issues: tabs de escopo (All/Assigned/Created/My Agents), 3 visões, agrupar por status/assignee.
- Search: command palette (cmdk) Ctrl/Cmd+K, grupos (Issues/Projects/Pages/Commands/Members/Agents), teclado, highlight.
- Polish: micro-interações finais consistentes em toda a app.

## Escopo de paths
`AOP/web/src/app/{settings,inbox,my-issues}/**`, `components/{settings,inbox,my-issues,search}/**`.

## Aceite (UAT)
- [ ] Navegação completa sem 404; 10 abas de Settings; Cmd+K funcionando.
- [ ] build verde. **Print** em `AOP/.planning/evidence/AG-6-settings.png`.

## Evidência obrigatória
build + PRINT real no ledger raiz.

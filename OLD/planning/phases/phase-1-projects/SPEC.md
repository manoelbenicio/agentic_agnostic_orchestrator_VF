# SPEC — FASE 1 · Projects (UI + backend)
**Dono:** AG-2 · **Status:** ready · **Depende de:** F0 (tokens já existem; pode iniciar backend já)

## Discuss
Não há tela nem tabela/endpoints de Projects hoje. É a base estrutural (Projetos → Tasks).

## WHAT
- Backend: tabela Postgres `projects` (tenant_id, name, key, status, description, lead, timestamps) +
  endpoints `POST/GET(list)/GET{id}/PATCH/DELETE /projects`; vínculo task↔project.
- UI: lista + board; criar (modal: nome/key/ícone/status/lead/descrição); editar; excluir (confirmação);
  cards de progresso real (issues done/total); filtros (status/lead). Visual Indra HEX. Empty state real.

## Escopo de paths
`AOP/web/src/app/projects/**`, `components/projects/**`, `AOP/control-plane/projects_api/**`, rotas em `app/main.py`.

## Out of scope
Issues/Tasks (FASE 2).

## Aceite (UAT)
- [ ] Criar projeto A e B, editar, excluir — via UI contra API real (curls colados).
- [ ] Board e progresso refletem dados reais; sem mock.
- [ ] pytest + `npm run build` verdes. **Print** da tela em `AOP/.planning/evidence/AG-2-projects.png`.

## Evidência obrigatória
pytest + build + curls + PRINT real no ledger raiz.

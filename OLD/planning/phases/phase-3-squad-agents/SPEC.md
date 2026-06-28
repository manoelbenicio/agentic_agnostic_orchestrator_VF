# SPEC — FASE 3 · Squad Builder v2 + Agents
**Dono:** AG-3 · **Status:** ready (canvas base existe) · **Depende de:** F0

## Discuss
Canvas existe e salva topologia→ACL, mas faltam ops de nó (papel, excluir) e a tela Agents.

## WHAT
- Canvas (@xyflow/react): paleta + contagem por vendor; **definir papel por nó (worker↔Tech-Lead)**;
  **excluir nó in-canvas** (sem reload); salvar/validar topologia (vira ACL via `/squads/{id}/topology`);
  hub-and-spoke default-deny; conceder/revogar aresta lateral.
- Tela Agents: registry CRUD (label, vendor, papel, estado, saúde, runtime/pane, seat).

## Escopo de paths
`AOP/web/src/app/{squad-builder,agents}/**`, `components/{squad-builder,agents}/**`. Lê control-plane/HerdMaster read-only.

## Aceite (UAT)
- [ ] Promover nó a Tech-Lead e excluir nó funcionam sem reload.
- [ ] Topologia do canvas vira regra ACL real (default-deny lateral comprovado).
- [ ] build verde. **Print** em `AOP/.planning/evidence/AG-3-squad.png`.

## Evidência obrigatória
build + curls topology/agents + PRINT real no ledger raiz.

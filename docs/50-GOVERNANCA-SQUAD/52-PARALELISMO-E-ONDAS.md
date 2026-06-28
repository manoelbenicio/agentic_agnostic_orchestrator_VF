# 52 — Paralelismo, Ondas e Anticolisão

Objetivo: **máximo paralelismo** entre os 8 agentes, **sem** que um quebre o código do outro. O mecanismo é trabalhar em **ondas** com escopos disjuntos, isolamento físico e integração centralizada no TL.

## 1. Modelo de ondas

Uma **onda** é um conjunto de tarefas que podem rodar **em paralelo** porque seus escopos **não se sobrepõem** (arquivos/diretórios disjuntos). O TL fecha cada onda com integração + verificação antes de abrir a próxima.

```
Onda N: [CDX-1 escopo A] [CDX-2 escopo B] ... [GLM-1 escopo H]   (paralelo)
            │ check-in        │ check-in
            ▼                  ▼
        trabalho            trabalho
            │ check-out+evidência
            ▼
        TL: integra + roda verificação (doc 42) + resolve conflitos
            ▼
Onda N+1: ...
```

## 2. Regras de disjunção de escopo

O TL atribui escopos que **não compartilham arquivos**. Fronteiras naturais do repo:

| Fronteira | Diretório | Dono típico |
|-----------|-----------|-------------|
| Control-plane API | `control-plane/app/` | CDX-1 |
| Executores | `control-plane/executors/` | CDX-1/CDX-3 |
| FinOps | `control-plane/finops/` | CDX-2 |
| Coupling | `control-plane/coupling/` | CDX-3 |
| Frontend | `web/` | CDX-4 |
| Ops/observabilidade | `ops/`, `deploy/` | CDX-5 |
| Tracing/E2E | `control-plane/tracing/`, `e2e/` | GEM-1 |
| Testes/docs | `e2e/`, `docs/` | GLM-1 |

> **Arquivos compartilhados de alto risco** (ex.: `control-plane/app/main.py`, `core/`, schemas): só **um** agente por onda pode editá-los, e mudanças nesses arquivos passam por revisão do TL **antes** de qualquer outro escopo depender delas.

## 3. Isolamento físico (anticolisão)

Estratégias (escolha registrada como ADR — ver doc 91):

### Opção A — Git worktrees (recomendada)
Cada engenheiro trabalha em um **branch + worktree** dedicado; o TL faz merge sequencial:
```bash
git worktree add ../AOP-cdx1 feat/onda1-cdx1
git worktree add ../AOP-cdx2 feat/onda1-cdx2
# ... TL integra na main com merge revisado, um por vez
```
Vantagem: isolamento total de árvore de trabalho; zero colisão de arquivo em disco.

### Opção B — Branches no mesmo checkout
Menos isolamento (um working dir); exige disciplina de não rodar agentes simultâneos no mesmo dir. Não recomendada para 8 agentes.

### Isolamento de runtime de ops
Para evitar colisão nos artefatos de `/tmp`, cada agente que subir o stack deve usar diretórios próprios (ver doc 13):
```bash
export AOP_OPS_RUN_DIR=/tmp/aop-run-cdx1
export AOP_OPS_RUNTIME_DIR=/tmp/aop-runtime-cdx1
```
> ⚠️ **Atenção a portas:** o stack usa portas fixas (8090, 13000, etc.). Dois agentes não podem subir o stack completo na **mesma** máquina ao mesmo tempo sem conflito de porta. Recomenda-se: **um** ambiente de runtime compartilhado controlado pelo TL, e os engenheiros trabalham em código/branches sem subir o stack simultaneamente — ou usar máquinas/containers separados.

## 4. Ordem de dependência entre ondas (sugerida)

Baseada nos bloqueadores reais (doc 34/35):

1. **Onda 0 — Fundações & correções de dívida:** corrigir asserção do smoke (`/health`), `BACKUP_ROOT`, paths legados do `status360.py`, `requirepass` do Redis. (escopos pequenos, muito paralelizáveis)
2. **Onda 1 — Adaptadores nativos por vendor + rastreamento até conclusão** (executores). Desbloqueia FinOps real.
3. **Onda 2 — FinOps automático + agregações multidimensionais** (modelo/task/agente/Kanban) + exporter dinâmico.
4. **Onda 3 — Frontend de FinOps granular + dashboards Grafana.**
5. **Onda 4 — Carga, verificação E2E real, hardening.**

> Identidade/billing (fase 2/3) ficam **fora** dessas ondas iniciais, por decisão do produto.

## 5. Definição de "onda concluída"

O TL só fecha uma onda quando:
- [ ] Todos os check-outs têm **evidência** (doc 53).
- [ ] `smoke_e2e.py` (corrigido) passa (doc 41).
- [ ] Itens relevantes do checklist (doc 42) verdes.
- [ ] Sem conflito pendente; main integra limpo.
- [ ] Nada fora de escopo foi tocado sem aprovação.

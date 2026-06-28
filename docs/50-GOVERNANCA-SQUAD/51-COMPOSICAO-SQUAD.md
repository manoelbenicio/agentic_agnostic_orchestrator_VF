# 51 — Composição da Squad

A AOP será construída por uma **squad agêntica de 8 agentes**, coordenada por um Tech Lead. Esta página define quem é quem, papéis e responsabilidades.

## 1. Roster (8 agentes)

| # | Codinome (sugerido) | Modelo | Papel | Especialidade |
|---|---------------------|--------|-------|---------------|
| 1 | **TL** | **Claude Opus 4.8** | Tech Lead / Orquestrador | coordenação, design, revisão, merge, anticolisão |
| 2 | CDX-1 | Codex 5.5 High Thinking | Engenheiro | control-plane / executores |
| 3 | CDX-2 | Codex 5.5 High Thinking | Engenheiro | FinOps / persistência |
| 4 | CDX-3 | Codex 5.5 High Thinking | Engenheiro | coupling HerdMaster/Herdr |
| 5 | CDX-4 | Codex 5.5 High Thinking | Engenheiro | frontend / Indra DSS |
| 6 | CDX-5 | Codex 5.5 High Thinking | Engenheiro | observabilidade / ops |
| 7 | GEM-1 | Gemini 3.1-PRO | Engenheiro | tracing / tempo real / E2E |
| 8 | GLM-1 | GLM52 | Engenheiro | testes / verificação / docs |

> Os codinomes são sugestão; o que importa é **estabilidade do identificador** ao longo do ledger (check-in/out usa o nome do agente). Ajuste a coluna de especialidade conforme a distribuição de ondas (doc 52).

## 2. Papéis e autoridade

### Tech Lead (Opus 4.8) — único coordenador
- Define ondas e atribui escopo **disjunto** a cada engenheiro (doc 52).
- É o **único** autorizado a fazer merge/integração entre escopos.
- Resolve conflitos, revisa PRs/diffs, valida evidências de check-out.
- Mantém o ledger de check-in/out consistente (doc 53).
- Mapeia-se ao papel `orchestrator` do ACL (agente `cli`, pode `dispatch`/`reassign`).

### Engenheiros (Codex/Gemini/GLM) — workers
- Executam apenas o escopo atribuído na onda corrente.
- **Obrigatório** check-in antes e check-out depois (doc 53).
- Não tocam arquivos fora do seu escopo sem aprovação do TL.
- Mapeiam-se ao papel `worker` do ACL (só falam com o `cli`/TL; sem comunicação lateral).

## 3. Alinhamento com o ACL do HerdMaster

A hierarquia da squad espelha o ACL `default_policy = deny` gerado em `herdmaster.config.toml` (ver doc 14):
- `orchestrator` (TL) → `can_send_to = ["*"]`, `can_dispatch_tasks = true`.
- `worker` (engenheiros) → `can_send_to = ["cli"]`, sem dispatch.

Isso significa que, **no produto**, a comunicação entre workers é negada por padrão (provado no smoke E2E, doc 41). **Na governança humana/agêntica**, o mesmo princípio: engenheiros coordenam **através** do TL, não lateralmente.

## 4. Princípio anticolisão (resumo)

> "Nenhum agente quebra o código de outro." — requisito explícito do produto.

Garantido por: (a) escopos disjuntos por onda, (b) isolamento de arquivos/worktrees, (c) ledger obrigatório, (d) merge centralizado no TL. Detalhes em [`52-PARALELISMO-E-ONDAS.md`](52-PARALELISMO-E-ONDAS.md) e [`54-COORDENACAO-TECH-LEAD.md`](54-COORDENACAO-TECH-LEAD.md).

## 5. Mapa squad → blocos de documentação

| Agente | Documentos-guia primários |
|--------|---------------------------|
| TL (Opus) | todos; especialmente 54, 53, 42 |
| CDX-1 | 31, 34 |
| CDX-2 | 35, 31 |
| CDX-3 | 33, 34 |
| CDX-4 | 32 |
| CDX-5 | 21–25, 23 |
| GEM-1 | 31 (tracing/WS), 41, 43 |
| GLM-1 | 41, 42, este conjunto de docs |

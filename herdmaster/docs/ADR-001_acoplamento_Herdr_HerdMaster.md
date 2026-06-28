# ADR-001 — Acoplamento Herdr ↔ HerdMaster (Opção 2 + Reconexão)

> **Tipo:** Architecture Decision Record
> **Data:** 2026-06-21
> **Decidido por:** Stakeholder + Tech Lead (GLM-5.2)
> **Status:** APROVADO — pendente de implementação (escalar ao Codex)
> **Substitui:** comportamento implícito do PRD (NFR-009 desacoplado puro)

---

## Decisão

**Acoplamento SUAVE (Opção 2) com mecanismo de reconexão/retry controlado pelo operador.**

Ao iniciar o Herdr, o HerdMaster sobe automaticamente junto (via plugin/hook do Herdr). Se o
HerdMaster falhar ao subir, o **Herdr continua funcionando** e exibe um aviso claro; o operador pode
**retentar a inicialização/conexão** sem reiniciar o Herdr.

### Por que (justificativa)
- Entrega a experiência "ligou o Herdr → orquestração disponível automaticamente" desejada pelo
  stakeholder.
- **Preserva o NFR-009** (resiliência): um bug no HerdMaster NÃO derruba o Herdr nem o trabalho dos
  agentes. HerdMaster não vira ponto único de falha.
- Reconexão dá controle operacional: recuperar a orquestração sem downtime do ambiente.

---

## Requisitos derivados (FRs novos — para o roadmap)

| ID | Requisito | Prioridade |
|----|-----------|------------|
| FR-AC-01 | Ao iniciar o Herdr, disparar a inicialização do HerdMaster automaticamente (plugin/hook de boot). | P0 |
| FR-AC-02 | Se o HerdMaster falhar ao subir, o Herdr SEGUE rodando e registra/exibe aviso claro com o motivo. | P0 |
| FR-AC-03 | Mecanismo de **reconexão/retry manual**: comando/ação para o operador retentar subir o HerdMaster sem reiniciar o Herdr. Ex.: `herdmaster start --retry` ou ação no plugin/TUI. | P0 |
| FR-AC-04 | **Retry automático com backoff**: na falha de boot, tentar reconectar N vezes com espera crescente antes de cair para o modo "aviso/manual". | P1 |
| FR-AC-05 | **Health/heartbeat de acoplamento**: a TUI/CLI mostra o estado do vínculo Herdr↔HerdMaster (conectado / degradado / desconectado) e o último erro. | P1 |
| FR-AC-06 | **Detecção de queda em runtime**: se o HerdMaster cair DEPOIS de subir, detectar e oferecer reconexão (não só no boot). | P1 |
| FR-AC-07 | Idempotência: retentar quando já está rodando não deve criar processo duplicado nem socket órfão. | P0 |

---

## Como deve se comportar (cenários)

1. **Boot feliz:** liga Herdr → HerdMaster sobe → estado "conectado". Tudo integrado.
2. **Falha no boot:** liga Herdr → HerdMaster falha (ex.: socket em uso, config inválida) →
   Herdr segue + aviso "HerdMaster degradado: <motivo>" → operador roda o retry → sobe → "conectado".
3. **Queda em runtime:** HerdMaster estava rodando e caiu → Herdr detecta → estado "desconectado" +
   alerta → retry automático (backoff) → se esgotar, aguarda retry manual.
4. **Retry quando já OK:** operador manda retry e já está conectado → no-op idempotente, sem duplicar.

---

## Implicações de implementação (para o Codex avaliar)

- **Mecanismo de boot conjunto:** plugin do Herdr (`herdr plugin install herdmaster`) com hook de
  inicialização, OU script wrapper que o Herdr chama no start. (PRD §14.1 "Option 3"; RESEARCH doc
  "Plugin-based orchestration" confirma suporte a manifest actions + event hooks.)
- **Reconexão:** a CLI já tem `start`/`stop`/`status`; adicionar `herdmaster reconnect` (ou
  `start --retry`) que: verifica se já há instância (idempotência FR-AC-07), limpa sockets órfãos,
  e sobe novamente. Reaproveitar a lógica de `_run_control_plane`.
- **Estado de acoplamento:** expor em `GET /status` (campo tipo `coupling: connected|degraded|
  disconnected` + `last_error`) e refletir na TUI (já tem painel de alertas — FR-307).
- **Retry com backoff:** reaproveitar o padrão de backoff que já existe no DispatchInjector.
- **Detecção de queda:** o próprio Herdr (via plugin) ou um supervisor leve monitora o PID/socket do
  HerdMaster.

---

## Relação com os outros itens do RCA

Este ADR se conecta diretamente ao épico de **Gerência de Agentes + Sincronização Herdr** (INC-003):
quando o HerdMaster sobe (no boot acoplado), é o momento natural de **sincronizar os agentes do Herdr
para a tabela `agents`** (`agent_list()` → `upsert`). Ou seja, FR-AC-01 (boot) deve disparar a sync
do INC-003. Isso resolve, de uma vez:
- INC-001 (haverá agentes reais; e o seed `cli` cobre ações do operador)
- INC-002/INC-003 (tabela `agents` populada → Modo Projeto funciona)
- A experiência "ligou Herdr → tudo pronto".

---

## Decisão registrada

> Stakeholder (2026-06-21): "Concordo a opção 2 e quando falhar temos que ter um mecanismo ou botão
> para tentar reconectar novamente, retentar coisas do tipo."

Tech Lead: aprovado. FR-AC-01..07 entram no épico de regularização para o Codex, com FR-AC-01/02/03/07
como P0 (mínimo para a experiência decidida).

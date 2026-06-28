# 34 — Execução Dual-Mode (Terminal / Socket)

Origem da verdade: `control-plane/executors/terminal.py`, `executors/socket.py`, `executors/events.py`, `core` (`TaskEnvelope`, `LifecycleStatus`, `OperationMode`).

> ⚠️ **Esta página documenta o estado REAL do código, incluindo stubs.** Ler com atenção: há lacunas que impactam diretamente a meta de "testar FinOps com agentes reais".

## 1. Modos de operação

`OperationMode.TERMINAL` (Herdr, panes) e `OperationMode.SOCKET` (HerdMaster, fila HTTP). O `POST /tasks` cria um `TaskEnvelope` e o roteia ao executor do modo escolhido, emitindo eventos de ciclo de vida: `QUEUED → CLAIMED → RUNNING → (BLOCKED|DONE|FAILED)`.

---

## 2. TerminalExecutor (`executors/terminal.py`)

`HerdrRuntimeAdapter` envolve o `HerdrAdapter` do HerdMaster: `spawn` (pane), `send` (texto no pane), `read_state` (mapeia estado), `stop` (fecha pane), `meter` (seat_seconds).

Ciclo em `dispatch`:
```text
QUEUED → spawn → CLAIMED → send(prompt) → RUNNING → read_state(uma vez) → meter → DONE
```

### ⚠️ Stubs verificados
1. **Rastreamento incompleto até a conclusão:** `read_state(runtime)` é chamado **uma única vez**. Se o estado não for `BLOCKED`, o executor já emite **`DONE`** — **não** faz polling até o agente realmente terminar. Ou seja, `DONE` aqui significa "tarefa despachada e lida uma vez", não "trabalho concluído".
2. **Metering zerado por padrão:** `meter()` usa `seat_seconds = hint.get("seat_seconds", 0)`. Sem `usage_hint`, o seat metering é **0**. Os eventos carregam `cost_refs` do metering, mas não há custo real computado aqui.

---

## 3. SocketExecutor (`executors/socket.py`)

`HerdMasterHttpQueueClient` fala com a API do HerdMaster: `enqueue` (`POST /tasks`), `claim` (`GET /tasks?assigned_to=...`), `mark_running` (`PATCH /tasks/{id}` → `in_progress`), `poll` (`GET /tasks/{id}`).

Ciclo em `dispatch`:
```text
enqueue → QUEUED → claim → CLAIMED → mark_running → RUNNING → _poll_terminal_status
```

### ⚠️ Stub verificado — `max_polls=1`
`_poll_terminal_status` itera `range(max(1, self.max_polls))`. O **default é `max_polls=1`** (e o wiring instancia `SocketExecutor(..., max_polls=1)` em todos os caminhos). Com 1 poll:
- Se o `poll` retornar estado terminal (`done/failed/blocked`), emite esse estado.
- Senão, emite `DONE` com a mensagem *"socket dispatch accepted; terminal completion will be reported by queue polling"*.

Ou seja, o socket-mode **também declara `DONE` após um único poll** — não acompanha a tarefa até a conclusão real. O mapeamento de estados (`_map_queue_state`) é robusto, mas só é exercido uma vez.

---

## 4. ❌ Lacuna crítica — FinOps NÃO é alimentado pelos executores

**Verificado:** nenhum executor chama `FinOpsEngine.record_token_usage` nem `record_seat_usage` durante o `dispatch`. O custo só entra no sistema por chamada HTTP **manual**:

```
POST /finops/costs/token
POST /finops/costs/seat
```

Consequência direta para a meta do projeto: **rodar uma tarefa com agente real NÃO gera custo automaticamente**. O FinOps fica "vazio" a menos que algo faça o POST. Hoje, só o smoke E2E faz esses POSTs explicitamente (doc 41).

> Esta é a lacuna nº1 a fechar antes de "testar FinOps com agentes reais". Plano em [`35-FINOPS-E-CUSTOS.md`](35-FINOPS-E-CUSTOS.md) §5 e pesquisa em [`90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md`](../90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md).

---

## 5. Dependência: adaptadores nativos por vendor

Para extrair **tokens reais** e **estado real** de cada agente (Codex, Gemini, GLM, Kiro...), é preciso de **adaptadores nativos por vendor** que:
- leiam o uso de tokens (input/output, modelo) da resposta de cada CLI/SDK;
- alimentem `record_token_usage` com a `Attribution` correta (tenant/projeto/issue/agente/runtime);
- façam polling até estado terminal (substituindo `max_polls=1` por loop com timeout/budget).

Sem isso, o dual-mode permanece um esqueleto funcional para contrato/topologia, mas não para FinOps de produção.

---

## 6. Verificação

```bash
# Disparar uma task socket e ver a sequência de eventos:
curl -s -X POST http://127.0.0.1:8090/tasks -H 'Content-Type: application/json' -d '{
  "task_id":"t-sock-1","tenant_id":"t1","project_id":"p1","issue_id":"i1",
  "assignee_runtime":"agente-x","prompt":"ping","operation_mode":"socket","seat_seconds":5
}' | python3 -c "import sys,json;d=json.load(sys.stdin);print([e['status'] for e in d['events']])"

# Esperado (com HerdMaster degradado/stub): ['queued','claimed','running','done']
# Confirmar que NENHUM custo foi gerado automaticamente:
curl -s http://127.0.0.1:8090/finops/projects/t1/p1/rollup | python3 -m json.tool
# record_count deve continuar 0 até um POST manual em /finops/costs/*
```

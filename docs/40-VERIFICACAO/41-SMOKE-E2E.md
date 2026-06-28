# 41 — Smoke E2E

Origem da verdade: `e2e/smoke_e2e.py`, `e2e/REPORT.md`, `e2e/evidence.json`.

## 1. O que o smoke valida

`e2e/smoke_e2e.py` exercita o control-plane em `AOP_E2E_BASE_URL` (default `http://127.0.0.1:8090`) e gera `evidence.json` + `REPORT.md`. Checagens:

| Check | O que prova |
|-------|-------------|
| `health` | `GET /health` responde |
| `ready` | `GET /health/ready` = ready (PG+Redis) |
| `metrics` | `/metrics` contém `aop_control_plane_up 1` |
| `topology_lateral_block` | ACL default-deny: TL↔worker permitido, **worker↔worker bloqueado** |
| `socket_lifecycle` | `POST /tasks` socket → `['queued','claimed','running','done']` |
| `terminal_lifecycle` | `POST /tasks` terminal → último status `done` |
| `trace_filters` | trace por agente e por runtime retornam o evento postado |
| `websocket_trace` | `/ws/tracing/agents/{id}` entrega evento |
| `finops_rollup` | 2+ registros de custo e `total_cost_usd > 0` |

Cria 3 agentes (Tech Lead `orchestrator`, Worker A/B `worker`), salva topologia, valida ACL aplicando o `AclEngine` do HerdMaster sobre a ACL efetiva retornada por `/squads/{id}/topology`.

---

## 2. Como rodar

```bash
# Pré: stack de pé (start.sh) com control-plane em :8090
export AOP_E2E_BASE_URL=http://127.0.0.1:8090
python3 AOP/e2e/smoke_e2e.py
# saída: JSON com result/run_id/checks; grava e2e/evidence.json e e2e/REPORT.md
```

Opcional: instalar `websockets` para o check de WS (`pip install websockets`), senão o check marca `available=false`.

---

## 3. ⚠️ Discrepância conhecida — asserção de `/health`

O smoke faz:
```python
assert_equal(health, {"status": "ok"}, "health")
```
Mas o `app/main.py` **atual** retorna:
```python
{"status": "ok", "coupling": _coupling_health(state)}
```

Ou seja, `health != {"status":"ok"}` (tem a chave `coupling`). **Contra o código atual, essa asserção falha.** O `e2e/REPORT.md` arquivado (run `e2e-20260626T044259Z`, tudo `passed`) foi gerado contra uma versão **anterior** do `/health` (sem `coupling`) — confirmado pelo próprio gap registrado no relatório: *"GET /health does not expose coupling_status yet"*.

**Ação para a squad:** corrigir o smoke para asserir o subconjunto, p.ex.:
```python
assert_equal(health.get("status"), "ok", "health status")
assert_true("coupling" in health, "health expõe coupling")
```
Registrado em [`90-DECISOES/91-ADRs.md`](../90-DECISOES/91-ADRs.md) como dívida de teste.

---

## 4. Gaps já reconhecidos pelo próprio smoke

Do `evidence.json`/`REPORT.md` (escritos pelo script):
1. **Sem endpoint público de send_message/handoff** — o bloqueio lateral foi provado aplicando o `AclEngine` à ACL efetiva, não via uma rota de mensagem. (Nota: hoje existe `POST /squads/{id}/messages`, mas o smoke não o exercita.)
2. **HerdMaster :8080 retornou 401 sem Bearer** no ambiente do run → socket-mode usou o **fallback** (ADR-001) a menos que um cliente tokenizado seja usado.
3. **`/health` não expunha `coupling`** no run arquivado (hoje expõe — daí a discrepância do §3).

---

## 5. Interpretação honesta dos "passed"

O smoke validar `socket_lifecycle = ['queued','claimed','running','done']` **não** significa que a tarefa foi executada por um agente real até a conclusão — significa que o executor **emitiu** essa sequência (lembrar dos stubs `max_polls=1` e `read_state` único, doc 34). O mesmo vale para `finops_rollup`: prova que o **POST manual** de custo agrega corretamente, **não** que executores alimentam custo automaticamente.

> O smoke é um excelente **teste de contrato/topologia**. Ele **não** é prova de execução real de ponta a ponta com agente nem de FinOps automático. Esses dois pontos são o foco do gate em [`42-CHECKLIST-TEST-READY.md`](42-CHECKLIST-TEST-READY.md).

---

## 6. Verificação

```bash
python3 AOP/e2e/smoke_e2e.py | python3 -m json.tool
cat AOP/e2e/REPORT.md
python3 -c "import json;d=json.load(open('AOP/e2e/evidence.json'));print(d['result']);print(d['checks'])"
```

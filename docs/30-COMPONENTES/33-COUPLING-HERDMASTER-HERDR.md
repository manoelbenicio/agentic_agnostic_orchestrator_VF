# 33 — Acoplamento HerdMaster / Herdr

Origem da verdade: `control-plane/coupling/wiring.py`, `coupling/hm_client.py`, `coupling/models.py`, `executors/*`.

## 1. Conceito

A AOP **não reimplementa** orquestração de baixo nível: ela acopla dois sistemas do projeto irmão **Herdr/HerdMaster**:

- **Herdr** — multiplexador/engine "Order" para execução em **terminal** (panes). Acesso via **socket AF_UNIX** (`~/.config/herdr/herdr.sock`).
- **HerdMaster** — control plane HTTP (`:8080`) com fila de tarefas e ACL. Acesso via **HTTP** com Bearer token.

O acoplamento escolhe adaptadores **reais** quando disponíveis e **degrada graciosamente** quando não (ADR-001 / NFR-009).

---

## 2. `build_coupled_executors` (wiring)

```python
def build_coupled_executors(*, fallback_terminal_adapter, fallback_queue_client,
                            herdmaster_url="http://127.0.0.1:8080",
                            herdmaster_token=None, herdr_socket_path=None) -> CoupledExecutors:
```

Fluxo:
1. **Probe Herdr** (`herdr_socket_probe`) — conecta no socket AF_UNIX e faz um `agent.list` JSON-RPC. Sucesso = `result` presente sem `error`.
2. **Probe HerdMaster**:
   - com token → `herdmaster_authenticated_probe(url, token=...)` (envia `Authorization: Bearer`).
   - sem token → `herdmaster_http_probe(url)` (sem auth; HerdMaster responde 401 → probe falha).
3. **Terminal executor**: se Herdr disponível → `TerminalExecutor(HerdrRuntimeAdapter(HerdrAdapter(socket_path=...)))`; senão → `TerminalExecutor(fallback_terminal_adapter)` e registra `"terminal degraded: Herdr socket unavailable"`.
4. **Socket executor**: se HerdMaster disponível → `SocketExecutor(HerdMasterAuthClient|HerdMasterHttpQueueClient, max_polls=1)`; senão → `SocketExecutor(fallback_queue_client, max_polls=1)` e registra a causa.
5. **Status final**: `CouplingPhase.CONNECTED` se nenhum erro, senão `DEGRADED`, com `last_error` concatenando as causas.

> **Degradação graciosa é por design.** O sistema continua respondendo mesmo sem Herdr ou HerdMaster; apenas marca o lado degradado. Isso permite testar partes do stack isoladamente.

---

## 3. Probes (detalhe verificado)

### Herdr socket (`herdr_socket_probe`)
- Path: `socket_path` ou env `HERDR_SOCKET_PATH` ou `~/.config/herdr/herdr.sock`.
- Requer `socket.AF_UNIX` e arquivo existente; timeout 1s.
- Envia `{"jsonrpc":"2.0","method":"agent.list",...}` e valida resposta JSON.

### HerdMaster HTTP (`herdmaster_http_probe`)
- `GET {base}/status`, timeout 1s; ok se JSON com `ok` truthy.
- A variante **autenticada** (`herdmaster_authenticated_probe`, em `hm_client.py`) é a usada quando há token, e é a mesma chamada por `_coupling_health` no control-plane.

---

## 4. Reflexo no `/health`

`app/main.py::_coupling_health` reusa o probe autenticado:

```text
sem token              → status=degraded, last_error="HerdMaster token is not configured"
token + probe falhou   → status=degraded, last_error="HerdMaster HTTP unavailable"
token + probe ok       → status=connected, instancia HerdMasterHttpMessageBus
```

O `start.sh` só considera o control-plane "pronto" para reaproveitamento quando `coupling.status == connected` (`aop_control_plane_coupling_connected` em `common.sh`).

---

## 5. Message bus

Quando `connected`, o `state.message_bus = HerdMasterHttpMessageBus(base_url, token)`. É ele que entrega `POST /squads/{id}/messages`. Se o bus estiver indisponível na hora do envio, o endpoint responde **503 `message_bus_unavailable`** (com `trace_id` e `audit_event_id`).

---

## 6. Verificação

```bash
# Herdr socket presente?
ls -l ~/.config/herdr/herdr.sock 2>/dev/null || echo "sem socket Herdr (terminal-mode degradado)"

# HerdMaster status (sem token → espere 401):
curl -s -o /dev/null -w 'status(noauth) %{http_code}\n' http://127.0.0.1:8080/status

# HerdMaster autenticado:
curl -s -o /dev/null -w 'metrics(auth) %{http_code}\n' \
  -H "Authorization: Bearer $(tr -d '\r\n' </tmp/aop-ops-runtime/herdmaster.token)" \
  http://127.0.0.1:8080/metrics

# Coupling visto pelo control-plane:
curl -s http://127.0.0.1:8090/health | python3 -c "import sys,json;print(json.load(sys.stdin)['coupling'])"
```

---

## 7. Notas para a squad

- O `PYTHONPATH` do control-plane inclui `../HerdMaster/src` — imports `herdmaster.*` dependem disso (ver doc 11/13).
- O ACL `default_policy=deny` (no TOML gerado) é a base de segurança: workers só falam com o `cli` (TL). Provado no E2E (doc 41).
- A integração real Herdr usa o adaptador `HerdrAdapter` do HerdMaster (`herdmaster.herdr.adapter`). Sua maturidade é responsabilidade do projeto irmão; a AOP só o adapta via `HerdrRuntimeAdapter`.

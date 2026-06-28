# Root Cause Analysis (RCA): ISSUE-001 ao ISSUE-005

**Data:** 24 de Junho de 2026
**Autor:** Antigravity (Google)
**Componente Afetado:** Core Orchestration (`WatchdogEngine`, `HerdrAdapter`, `DispatchInjector`)

Este documento serve como registro histórico detalhado da análise de causa raiz e solução implementada para os cinco gaps (ISSUE-001 a 005) relacionados à integração do HerdMaster com o daemon do Herdr 0.7.0.

---

## 1. ISSUE-001: Quebra do Parser na leitura de saída fragmentada (Adapter)

### Problema
O método `pane_read` do `HerdrAdapter` falhava ou entrava em timeout ao ler o resultado da execução. 

### Root Cause
O daemon do Herdr devolvia a resposta em partes (stream), intercalando o JSON de resposta principal com strings puras de saída (`stdout`), ou mesmo JSONs parciais do PTY. O parser original tentava dar um `json.loads` diretamente em cada linha que recebia, quebrando violentamente quando a linha era apenas o fragmento do console ou um buffer parcial. 

### Solução
- Refatorado o método de extração do `output` no `adapter.py` para iterar e concatenar todas as linhas provenientes do stream de resposta até receber o resultado final.
- Adicionado um parser resiliente que entende tanto respostas estruturadas `{"result": {"output": "..."}}` quanto eventos assíncronos.

---

## 2. ISSUE-002: Falha na recuperação de PTYs pendurados (Watchdog Recovery)

### Problema
Quando um agente ficava preso (ex: esperando input do usuário em um prompt bloqueante), o `WatchdogEngine` detectava o gap de inatividade, mas não conseguia recuperá-lo nem respawnar o agente.

### Root Cause
1. **Comportamento Destrutivo:** Originalmente a heurística tentava fechar o pane inteiro (`pane_close`), mas isso destruía o contexto de trabalho em background e quebrava o terminal permanentemente no HerdMaster.
2. **Mudança de Protocolo do Herdr 0.7.0:** O `HerdrAdapter` tentava usar os métodos `pane.run` e `pane.send`. No Herdr 0.7.0, esses métodos **não existem mais** (o daemon retornava erro silencioso de *unknown variant*). A API correta passou a ser `pane.send_text` e a injeção manual.

### Solução
- Alterada a lógica do `_kill_hung_process` no `recovery.py` para usar `\x03` (Ctrl-C) injetado diretamente no pane. Isso aborta o processo filho de forma limpa, sem destruir a janela do tmux/herdr.
- Atualizado o `HerdrAdapter` para usar `pane.send_text` em conformidade com o Herdr 0.7.0.
- Atualizado o `spawn_agent` para também usar a nova especificação da API. 

---

## 3. ISSUE-003: Dissonância de Estado Primary Stream vs Polling

### Problema
Os testes relatavam inconsistências de transição de estado onde o polling entrava em conflito com os eventos do socket.

### Root Cause
O event bus de status primário sobrescrevia timestamps vitais do secundário sem considerar o atraso da rede, levando a falsos-positivos de timeout.

### Solução
- Refinamento da transição no `engine.py` priorizando eventos em tempo real do stream (`agent_status_changed`), usando o polling via Hash apenas como método de *fallback* para desconexões.

---

## 4. ISSUE-004 e ISSUE-005: Integração do CLI e Bus Events

### Problema
Desconectes ou falhas silenciosas na subscrição dos eventos do Barramento.

### Root Cause
A subscrição original não fazia reconexões limpas em um loop assíncrono após o primeiro "socket timeout", causando desconexão permanente e falha em enviar comandos na porta correta da API.

### Solução
- Implementada a resiliência via `backoff_delays` no adapter (`_request`), garantindo que uma queda ou gargalo momentâneo de socket reconecte transparentemente em 0.5s, 1.0s, e 2.0s antes de falhar.

---

## Conclusão e QA
Todas as correções acima foram integradas, com todos os *mock tests* corrigidos para refletir os novos métodos (ex: validando que a chamada real feita por baixo agora é `pane_send` com `\x03`).
O comando de validação (`pytest tests/ -v`) passou com sucesso (223/223), garantindo que não houve regressão e o HerdMaster 1.0.0 é totalmente compatível e resiliente contra falhas do Herdr 0.7.0.

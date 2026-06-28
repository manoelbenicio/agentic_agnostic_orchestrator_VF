# Documentação E2E: Arquitetura e Operações (Day 2)

Este documento foi elaborado para as equipes de Suporte e Operações (Day 2). Ele detalha o fluxo End-to-End (E2E) do sistema, a topologia de rede, arquitetura de software e os conceitos fundamentais para a operação conjunta do **Herdr** e do **HerdMaster**.

---

## 1. Fluxo de Inicialização (Como tudo começa?)

Quando você liga o computador ou servidor, o fluxo de inicialização segue uma hierarquia estrita para garantir que a infraestrutura suba antes da camada de inteligência (orquestração).

1. **Início pelo Herdr:** O componente principal que deve ser iniciado **sempre primeiro** é o `Herdr`. Ele é o daemon (serviço de background) responsável por gerenciar a infraestrutura de terminais.
2. **Gatilho Automático (Acoplamento Suave):** Conforme definido na nossa arquitetura (ADR-001), o Herdr possui um *hook* (gatilho) interno. Assim que o Herdr termina de carregar seus componentes básicos, ele **chama e inicia o HerdMaster automaticamente**.
3. **Resiliência:** Você pode ficar tranquilo: se por algum motivo o HerdMaster falhar ao subir (ex: porta ocupada), o Herdr **continua funcionando normalmente**. O operador será notificado e poderá forçar a reconexão manual (ex: via `herdmaster start --retry`).

**Resumo do Fluxo E2E de Boot:**
`OS Boot` ➔ `Inicia Herdr` ➔ `Abre Unix Socket` ➔ `Gatilho dispara HerdMaster` ➔ `HerdMaster conecta no Socket do Herdr` ➔ `Sistema Pronto`.

---

## 2. Topologia e Componentes (Quem faz o quê?)

### O Herdr (O Multiplexador Agent-Aware)
O Herdr é a base da infraestrutura. Ele é um **multiplexador de terminal agent-aware** construído em Rust (usando `ratatui`), sendo extremamente leve (um único binário sem necessidade de Electron ou interface web).
- **O que ele faz:** Gerencia processos, janelas (Panes), abas (Tabs) e espaços de trabalho (Workspaces). 
- **É igual ao TMUX?** Sim e Não. A fundação de multiplexação de PTYs (terminais) e divisão de telas é exatamente igual ao `tmux` ou `screen`. A grande diferença é que o Herdr é **Agent-Aware** (Ciente dos Agentes). Ele rastreia ativamente o estado semântico de cada janela (se o agente está *idle*, *working*, *blocked* ou *done*) lendo heurísticas de saída de tela e processos em foreground, sem precisar de configuração zero para agentes suportados (como Codex, Claude Code, Pi, etc.).
- **Múltiplas Janelas:** Quando abrimos 1, 5, 10 ou 20 janelas simultâneas, o Herdr está criando **Sessões PTY isoladas**. Cada janela é um processo independente. Os *Workspaces* rolam para o estado mais urgente para que a equipe escaneie rapidamente a lista completa.
- **Persistência de Sessão:** O Herdr sobrevive a *detaches* de cliente. As sessões restauram as janelas após um reinício completo, com histórico recente de tela.
- **Gestão de Hardware:** A alocação real de CPU e Memória RAM é feita pelo próprio **Sistema Operacional (Kernel)**. O Herdr não atua como hypervisor para limitar RAM ativamente; ele gerencia o ciclo de vida da interface de texto e do processo do shell.

### O HerdMaster (Control Plane / Orquestrador)
O HerdMaster é o "cérebro" ou Control Plane. Ele não cria terminais e não gerencia hardware.
- **O que ele faz:** Ele dita **o que** deve rodar em cada janela do Herdr. Ele gerencia as filas de tarefas, decide qual agente (IA) vai fazer qual trabalho, lê o status da tela (via Herdr) e atua se algo der errado (ex: agente travou, o HerdMaster manda o Herdr matar a janela).

---

## 3. Topologia de Rede e Portas (Comunicação)

Para que o sistema funcione de forma segura e eficiente, usamos dois tipos de conexão. Aqui entra a explicação técnica sobre a topologia de portas e o conceito de **BIND**.

### O que significa "BIND"?
No jargão de redes e sistemas, fazer um **"Bind"** (ligação/vínculo) significa que um programa reservou um endereço e uma porta específica na placa de rede para "ouvir" conexões. 
- Se você faz um *bind* em `0.0.0.0`, o sistema ouve a internet/rede inteira (Inseguro, Bidirecional externo).
- Se você faz um *bind* em `127.0.0.1` (localhost), o sistema só ouve conexões vindas do **próprio computador** (Seguro, Fechado para a rede externa).

### Matriz de Rede Necessária

| Componente | Tipo de Conexão | Porta / Caminho do Bind | Direção | Finalidade |
|:---|:---|:---|:---|:---|
| **Herdr (Daemon)** | Unix Domain Socket (UDS) | `~/.config/herdr/herdr.sock` | Interna (Local) | Canal de comunicação ultra-rápido entre o Herdr e o HerdMaster. **Não usa porta TCP/IP**. Funciona como um arquivo no disco. |
| **HerdMaster (API)** | TCP IPv4 | `127.0.0.1` porta **8080** | Interna (Local) | API REST + `/metrics` para Prometheus. O bind é feito em localhost, então a porta 8080 precisa estar livre no servidor. |
| **Prometheus** | TCP IPv4 | `127.0.0.1` porta **9090** | Interna (Local) | Scrape de métricas do HerdMaster a cada 5s. 7 alert rules ativas. |
| **Alertmanager** | TCP IPv4 | `127.0.0.1` porta **9093** | Interna (Local) | Roteamento de alertas para webhook de remediação. |
| **Webhook Remediation** | TCP IPv4 | `127.0.0.1` porta **9099** | Interna (Local) | Recebe alertas e executa purge via `DELETE /agents/{id}` na API do HerdMaster. |
| **Grafana** | TCP IPv4 | `127.0.0.1` porta **3000** | Interna (Local) | Dashboard "Registry Integrity" com 6 painéis de métricas. |

*(Nota de Firewall: Como todos os componentes rodam usando `localhost` e `Unix Sockets`, **nenhuma porta externa de firewall precisa ser aberta** para a internet. Toda a topologia é fechada e segura dentro da própria máquina).*

---

## 4. Diagrama de Arquitetura Técnica

Abaixo está o diagrama arquitetural detalhando a topologia de comunicação entre hardware, software e rede.

```mermaid
flowchart TD
    %% Nós Externos
    User((Operador/Usuário))

    subgraph Server_OS [Servidor / OS Kernel (Gestão de Hardware RAM/CPU)]
        
        subgraph HerdMaster_Layer [Control Plane: HerdMaster]
            API[HerdMaster API\nTCP 127.0.0.1:8080]
            Watchdog[Watchdog & Recovery]
            DB[(SQLite Local)]
            
            API --- Watchdog
            Watchdog --- DB
        end
        
        subgraph Socket_Layer [Comunicação IPC]
            UDS{{Unix Socket\nherdr.sock}}
        end
        
        subgraph Herdr_Layer [Infraestrutura: Herdr Multiplexador]
            Daemon[Herdr Daemon]
            
            subgraph PTYs [Pseudo-Terminals (TMUX like)]
                Pane1[Janela 1\nAgente Codex]
                Pane2[Janela 2\nAgente Python]
                PaneN[Janela N...]
            end
            
            Daemon -->|Spawn / Kill / Read| Pane1
            Daemon -->|Spawn / Kill / Read| Pane2
            Daemon -->|Spawn / Kill / Read| PaneN
        end
    end

    %% Relações e Fluxos
    User == "Usa CLI (herdmaster status)" ==> API
    User -. "Inicia o sistema" .-> Daemon
    
    Daemon -- "Hook Automático" --> HerdMaster_Layer
    Watchdog == "Envia Comandos (pane.send_text)\nEscuta Eventos" ==> UDS
    UDS <== "Respostas e Logs" ==> Daemon

    classDef core fill:#2a4d69,stroke:#fff,stroke-width:2px,color:#fff;
    classDef infra fill:#4b86b4,stroke:#fff,stroke-width:2px,color:#fff;
    classDef sys fill:#adcbe3,stroke:#333,color:#000;
    
    class API,Watchdog,DB core;
    class Daemon,Pane1,Pane2,PaneN infra;
    class Server_OS,Socket_Layer sys;
```

### Explicação do Diagrama para o Day 2
1. O Usuário opera a linha de comando enviando requisições HTTP para a porta `8080` (HerdMaster).
2. O HerdMaster calcula a prioridade e a saúde do sistema usando o `SQLite`.
3. O HerdMaster se comunica com o Herdr usando o arquivo físico `herdr.sock` (Unix Socket).
4. O Herdr recebe a ordem e aloca recursos no Sistema Operacional, abrindo uma "Janela" (PTY). Se a janela travar, o HerdMaster envia um sinal `\x03` (Ctrl-C) pelo mesmo socket, e o Herdr repassa esse sinal para a Janela específica, matando apenas o processo interno sem derrubar o resto.

---

## 5. Protocolo de Comunicação entre Agentes (ACL)

> **Atualizado:** 2026-06-25 | Fonte: `acl/engine.py`, `config.toml`, `squad.py`

### Política Padrão: DENY

O HerdMaster usa `default_policy = "deny"`. **Toda comunicação é bloqueada por padrão.** Apenas o que está explicitamente configurado no ACL passa.

### Roles e Permissões

| Role | Quem é | Pode despachar tasks? | Pode falar com quem? |
|------|--------|----------------------|---------------------|
| `orchestrator` | CLI Operator, Kiro | ✅ SIM | **Qualquer agente** |
| `worker` | AGY, Codex, Flash35 | ❌ NÃO | Somente o `orchestrator` |
| `peer_reviewer` | (se configurado) | ❌ NÃO | `orchestrator` + outros `peer_reviewer` |
| `observer` | (monitoramento) | ❌ NÃO | Ninguém |

### Agentes que NÃO precisam de pane Herdr

| Agente | Motivo |
|--------|--------|
| `CLI Operator` (id=`cli`) | `role=orchestrator` — nunca recebe tasks. `herdr_pane=NULL` por design (`schema.py:17`). |

**Pergunta frequente:** "O CLI Operator precisa de pane?"
**Resposta:** Não. O `cli` é um seed agent de sistema. O campo `herdr_pane` é nullable by design. Tasks nunca são atribuídas a ele porque `squad.py:33` filtra orchestrators explicitamente.

### Fluxo de Comunicação

```
VOCÊ ────────────────────────────────► KIRO (Orchestrator)
  (via Antigravity/CLI)                     │
                                            │ despacha tasks (via DispatchInjector)
                                            ▼
                                    Workers (AGY_Opus-46 / Codex_#1 / Flash35...)
                                            │
                                            │ reportam resultado
                                            ▼
                                    KIRO (consolida e relata para você)
```

**Regra de ouro:** Você fala com Kiro. Kiro coordena os workers. Workers NÃO falam entre si sem passar pelo orchestrator.

---

## 6. Registry de Agentes em Produção (2026-06-25)

**7 agentes** — fonte: `herdmaster.db` verificado em 2026-06-25T15:37Z

| Label | Pane | Role | Modelo |
|-------|------|------|--------|
| CLI Operator | `cli` (sem pane) | orchestrator | sistema/seed |
| Kiro_Opus-48 | `w6:p7` | orchestrator | Kiro CLI V3, Claude Opus 4.8 High |
| AGY_Opus-46 | `w6:p1` | worker | Claude Opus 4.6 (Thinking) |
| AGY_Gemini_PRO-31 | `w6:p2` | worker | Gemini 3.1 Pro (High) |
| Codex_#1 | `w6:p5` | worker | gpt-5.5 medium |
| Codex_#2 | `w6:p6` | worker | gpt-5.5 medium |
| AGY_Flash35-High-Thinking | `w6:p8` | worker | Gemini 3.5 Flash (High) |

> [!WARNING]
> Qualquer agente fora desta lista que aparecer no DB é lixo de auto-registro do Herdr.
> Deletar com: `sqlite3 ~/.config/herdmaster/herdmaster.db "DELETE FROM agents WHERE id NOT IN ('cli','w6:p1','w6:p2','w6:p5','w6:p6','w6:p7','w6:p8');"`

Ver [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) para o registro completo com notas.


---

## 7. Comandos Operacionais (OPS)

> Aliases ativos no WSL `~/.bashrc` (shell interativo):

```bash
hm-status   # Estado completo (HerdMaster, Herdr, DB, agentes, prompts)
hm-start    # Inicia o Control Plane
hm-stop     # Para graciosamente (preserva tudo)
hm-restart  # Restart SEM apagar dados ou logs
hm-reset    # Reset soft (limpa resíduos, preserva DB)
hm-agents   # /chat new para todos os agentes (limpa contexto)
hm-flush    # FLUSH TOTAL — apaga DB+prompts (pede CONFIRMO)
```

Ver [`OPS_RUNBOOK.md`](OPS_RUNBOOK.md) para o runbook completo com diagnósticos e sequência de boot após `wsl --shutdown`.

---

## 8. Stack de Observabilidade (desde 2026-06-25)

### Arquitetura do loop de auto-remediacão

```
HerdMaster /metrics
    ↓ (scrape 5s)
Prometheus (7 alert rules)
    ↓ (FIRING)
Alertmanager
    ↓ POST /webhook/remediate
Webhook Server (porta 9099)
    ↓ DELETE /agents/{id}
HerdMaster HTTP API (porta 8080)
    ↓ (single DB writer)
SQLite DB — agente fantasma removido
    ↓ (próximo scrape)
Prometheus → unlisted=0, compliant=1 → RESOLVED
```

**Tempo de remediação observado: ~45s** (validado em 2026-06-25T16:15:27Z)

### Arquitectura single-writer

O webhook **não acessa o SQLite diretamente**. Toda escrita passa pela HTTP API do HerdMaster,
que é o único dono do banco. Isso elimina o erro `database is locked` definitivamente.

### Métricas chave

| Métrica | Valor esperado em operação normal |
|---------|-----------------------------------|
| `herdmaster_whitelist_compliant` | `1` |
| `herdmaster_unlisted_agents_total` | `0` |
| `herdmaster_agents_total` | `7` |

Ver [`OPS_RUNBOOK.md#9`](OPS_RUNBOOK.md) para comandos de verificação e Grafana dashboard.

# 📖 Agent Registry — HerdMaster Control Plane
**Versão:** 2026-06-25T16:17Z | **Fonte:** `herdmaster.db` + `config.toml` verificados em produção

> [!IMPORTANT]
> Este é o registro canônico oficial. **7 agentes** — 6 em panes Herdr + 1 seed de sistema.
> Use sempre os **LABELS** desta tabela em logs, dashboards Grafana, métricas Prometheus.
> Qualquer agente fora desta lista é **automaticamente bloqueado** pelo allowlist guard no `engine.py`.

---

## Regra de Ouro — Roles

```
role=orchestrator → NUNCA recebe tasks. Coordena, despacha, revisa.
role=worker       → Recebe e executa tasks via prompt injection (Herdr pane).
```

**Fonte:** [`squad.py:33`](../src/herdmaster/project/squad.py) — orchestrators são explicitamente excluídos do squad.

---

## Registry Completo (7 agentes canônicos)

### 🎯 Orchestrators (NUNCA recebem tasks)

| Label | ID/Pane | Tipo | Herdr Pane | Modelo / Observação |
|-------|---------|------|-----------|---------------------|
| **CLI Operator** | `cli` | system | `NULL` ✅ | Seed agent do sistema. Representa o operador/HerdMaster. **Não precisa de pane — nullable by design** (`schema.py:17`). |
| **Kiro_Opus-48** | `w6:p7` | kiro | `w6:p7` | Tech Lead. Kiro CLI V3, Claude Opus 4.8 High. Coordena squads, despacha tasks, faz revisão final. |

### ⚙️ Workers — Squad_Snippers (workspace w6)

| Label | Pane ID | Tipo | Modelo | Role |
|-------|---------|------|--------|------|
| **AGY_Opus-46** | `w6:p1` | agy | Claude Opus 4.6 (Thinking) | worker |
| **AGY_Gemini_PRO-31** | `w6:p2` | agy | Gemini 3.1 Pro (High) | worker |
| **Codex_#1** | `w6:p5` | codex | GPT-5.5 medium | worker |
| **Codex_#2** | `w6:p6` | codex | GPT-5.5 medium | worker |
| **AGY_Flash35-High-Thinking** | `w6:p8` | agy | Gemini 3.5 Flash (High) | worker |

---

## Mecanismo de Proteção — Allowlist Guard (implementado 2026-06-25)

### Como funciona

O `WatchdogEngine` possui um **allowlist guard** implementado em [`engine.py`](../src/herdmaster/watchdog/engine.py) que bloqueia na **origem** qualquer agente não listado em `config.toml`:

```python
# engine.py — _sync_agent() e _sync_primary_agent()
if self.config.agent_allowlist and agent.id not in self.config.agent_allowlist:
    log.debug("allowlist: ignoring unregistered Herdr pane %r", agent.id)
    return  # ← nunca chega ao DB
```

Configurado em `~/.config/herdmaster/config.toml`:

```toml
[watchdog]
agent_allowlist = [
  "cli",
  "w6:p1",
  "w6:p2",
  "w6:p5",
  "w6:p6",
  "w6:p7",
  "w6:p8",
]
```

### Defesa em Profundidade — 3 Camadas

| Camada | Mecanismo | Arquivo | Comportamento |
|--------|-----------|---------|---------------|
| **1 — Engine** | Allowlist guard em `_sync_agent()` | `watchdog/engine.py` | Phantom nunca entra no DB |
| **2 — Bootstrap** | `purge_unlisted_agents()` no boot | `ops/bootstrap.sh` | Limpa residuais do arranque |
| **3 — Observability** | Prometheus → Alertmanager → Webhook | `deploy/observability/` | Detecta e purga via HTTP API em ~45s |

### Por que este problema existia

O Herdr faz auto-discovery de **todos** os panes do workspace. Ao iniciar com múltiplos workspaces (w6 + w8), o `WatchdogEngine` registrava automaticamente panes de outras squads no DB. Isso era um false positive — os panes existem no Herdr mas não são agentes do nosso Control Plane.

**Raiz:** `WatchdogEngine._sync_agent()` chamava `AgentRepo.upsert()` para qualquer pane sem validar.
**Solução:** Allowlist guard na entrada do engine — zero escrita no DB para IDs não autorizados.

---

## Como Adicionar um Novo Agente

> [!CAUTION]
> Nunca adicione manualmente no DB sem registrar também no allowlist — o allowlist guard bloqueará o agente no próximo poll do watchdog.

Procedimento correto:

```bash
# 1. Adicionar ID ao allowlist em config.toml
nano ~/.config/herdmaster/config.toml
# → adicionar "w6:pN" em agent_allowlist

# 2. Adicionar mesmo ID em webhook_server.py
nano /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster/deploy/observability/remediation/webhook_server.py
# → adicionar "w6:pN" em AGENT_WHITELIST

# 3. Registrar no DB
sqlite3 ~/.config/herdmaster/herdmaster.db \
  "INSERT INTO agents (id, label, type, role, state, health, updated_at) \
   VALUES ('w6:pN', 'LABEL_DO_AGENTE', 'agy', 'worker', 'idle', 'healthy', datetime('now'));"

# 4. Restart para recarregar config
hm-restart
```

---

## Como Atualizar um Label no DB

```bash
sqlite3 ~/.config/herdmaster/herdmaster.db \
  "UPDATE agents SET label='NOVO_NOME', updated_at=datetime('now') WHERE id='w6:p1';"
```

---

## Por que o CLI Operator não tem pane Herdr?

O `CLI Operator` é um **seed agent** que representa ações do sistema/operador no Control Plane.
Ele **nunca executa tasks** — tasks são executadas por workers via prompt injection em panes Herdr.

Evidências no código-fonte:

1. **`schema.py:17`** — `herdr_pane TEXT` é nullable by design. Sem NOT NULL constraint.
2. **`squad.py:33`** — `role != "orchestrator"` filtra o CLI antes de qualquer atribuição de task.
3. **`injector.py:157`** — o erro `"has no resolvable Herdr pane"` só é atingido se uma task for incorretamente atribuída a um orchestrator.
4. **`ADR-001:75`** — *"o seed `cli` cobre ações do operador"* — nunca executa.

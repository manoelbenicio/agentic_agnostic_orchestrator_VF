# 42 — Checklist "Pronto para testar com agentes reais"

Gate objetivo para declarar a plataforma pronta para **testes com agentes reais** (Kanban, terminais, projetos, tarefas, FinOps) — a prioridade declarada do produto, antes de identidade/billing.

Cada item tem um **comando de verificação**. Marque ✅ só com evidência reproduzível.

## A. Infra base
- [ ] Postgres up e `pg_isready` ok
  ```bash
  docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  ```
- [ ] Redis up e `PONG`
  ```bash
  docker compose --env-file deploy/.env -f deploy/docker-compose.yml exec -T redis redis-cli ping
  ```
- [ ] `.env` real criado a partir do template; senhas trocadas
- [ ] (segurança) Redis com `requirepass` aplicado **ou** risco aceito e registrado (gap doc 13)

## B. Control-plane
- [ ] `/health` = ok e `/health/ready` = ready
  ```bash
  curl -s http://127.0.0.1:8090/health && curl -s http://127.0.0.1:8090/health/ready
  ```
- [ ] `coupling.status == "connected"` (HerdMaster acoplado, não degradado)
  ```bash
  curl -s http://127.0.0.1:8090/health | python3 -c "import sys,json;print(json.load(sys.stdin)['coupling']['status'])"
  ```
- [ ] `/openapi.json` lista todas as rotas esperadas (tasks, squads, agents, finops, tracing, projects, issues, settings, inbox, seats, sessions)

## C. HerdMaster / Herdr
- [ ] HerdMaster `:8080/metrics` responde 200 com Bearer
- [ ] Herdr socket presente (se terminal-mode for testado): `~/.config/herdr/herdr.sock`

## D. Frontend
- [ ] `:13000` responde 200
- [ ] Páginas-chave abrem: `/projects`, `/squad-builder`, `/finops`, `/live`, `/agents`
- [ ] DSS sem OKLCH (`grep -ri oklch web/src/app/globals.css` vazio)

## E. Observabilidade
- [ ] Prometheus/Grafana/Alertmanager/Blackbox/Remediação respondem (doc 23)
- [ ] Prometheus consegue raspar `/metrics` da AOP e do HerdMaster (token 644 ok)

## F. Fluxos funcionais (smoke)
- [ ] `smoke_e2e.py` roda — **corrigir a asserção de `/health`** antes (doc 41 §3)
  ```bash
  python3 AOP/e2e/smoke_e2e.py | python3 -m json.tool
  ```
- [ ] ACL default-deny comprovada (worker↔worker bloqueado)
- [ ] Ciclo de vida socket e terminal emitem estados esperados

## G. ⚠️ Bloqueadores para FinOps REAL (não cobertos pelo smoke)
Estes itens **não** estão prontos hoje (ver doc 34 e 35). São o que separa "contrato verde" de "FinOps de produção":

- [ ] **Executores alimentam FinOps automaticamente** (hoje ❌ — só POST manual)
- [ ] **Adaptadores nativos por vendor** extraem tokens/modelo reais (hoje ❌)
- [ ] **Rastreamento até conclusão real** (substituir `max_polls=1` / `read_state` único) (hoje ❌)
- [ ] **Rollup por modelo / task / agente / grupo / Kanban** (hoje ⚠️ só por tenant/projeto)
- [ ] **Exporter Prometheus dinâmico** (hoje ⚠️ `tenant-a`/`project-a` fixos)

## H. Operação
- [ ] `start.sh` / `stop.sh` idempotentes funcionam
- [ ] Backup `full` + `hourly` rodam e verificam (`BACKUP_ROOT` corrigido — doc 22)
- [ ] Runbook testado em pelo menos 1 cenário de falha (doc 24)

---

## Veredito de prontidão

| Camada | Pode testar agora? |
|--------|---------------------|
| Infra + control-plane + frontend + topologia/ACL | ✅ sim (com smoke corrigido) |
| Kanban / projetos / tarefas (contrato) | ✅ sim |
| **FinOps com agentes reais (custo automático/granular)** | ❌ **não** até fechar o bloco **G** |

> Conclusão honesta: a plataforma está pronta para **testes de contrato, topologia e UI** já. Para a meta específica de **"testar todo o monitoramento de custos via FinOps com agentes reais"**, o bloco **G** é pré-requisito obrigatório.

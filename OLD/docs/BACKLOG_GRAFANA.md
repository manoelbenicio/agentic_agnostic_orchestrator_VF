# Backlog — Customização do Grafana / Observabilidade (AOP + HerdMaster)

Registro das pendências de customização do Grafana, levantadas em 2026-06-26 a partir da
inspeção ao vivo dos dashboards. Itens marcados com prioridade (P1 = bloqueante, P2 = importante, P3 = melhoria).

> Acesso atual: Grafana só responde via IP do WSL (http://172.19.77.147:3000) porque os
> containers de observabilidade usam `network_mode: host` e o WSL2 não encaminha essas portas
> para o `localhost` do Windows. Prometheus :9090, Alertmanager :9093 idem.

## GRAF-01 (P1) — Painéis de tráfego de API "No data" (AOP API Traffic — Per Agent & Route)
Todos os painéis estão "No data": Total Requests, Success Rate, Error Count, p95 Latency,
Requests/Error per Route, Top Routes by Volume, Route Status Matrix, p50/p95/p99 Latency per Route,
Request Duration Heatmap, Requests by Method/Status Class/Status Code.
- Causa provável: control-plane não está emitindo as métricas `aop_api_*` (por rota/método/status)
  e/ou Prometheus não as scrapeia; nomes de métrica nas queries dos painéis podem não bater.
- Ação: instrumentar o control-plane (middleware de métricas por rota), expor `/metrics`, adicionar
  target no Prometheus, alinhar `expr` dos painéis às métricas reais.

## GRAF-02 (P1) — Targets Prometheus DOWN → painéis de saúde OFFLINE
No "HerdMaster — Squad Control Center", "API Health (E2E)" mostra `/status` e `/agents` OFFLINE.
- Causa: targets `herdmaster-internal-metrics` e/ou `herdmaster-remediation` fora do ar (ver TD14).
- Ação: religar/validar targets em `/api/v1/targets` (todos UP); garantir que o exporter do
  control-plane (`/status`, `/agents`) seja scrapeado.

## GRAF-03 (P1) — Registry Integrity: whitelist obsoleta (falso positivo "VIOLADO")
Painel "Registry Integrity — Anti-False-Positive Monitor" mostra Whitelist Compliance = VIOLADO,
Ghost Agents = 8, Actual 9 vs Expected 7.
- Causa: `AGENT_WHITELIST` hardcoded em `HerdMaster/deploy/observability/remediation/webhook_server.py`
  aponta para panes do workspace ANTIGO (`w6:*`); o roster real é `w8:*`.
- Ação: tornar a whitelist dinâmica (derivada do roster vivo do herdr) via serviço de reconciliação
  horário; webhook_server passa a ler whitelist de arquivo canônico. (EM ANDAMENTO nesta entrega.)

## GRAF-04 (P2) — FinOps & Tracing zerados
Dashboard "AOP — FinOps and Tracing": custo total $0, "Project Cost by Engine"/"FinOps Snapshot"
sem valores, "Token Burn Rate by Agent" e "Seat Seconds Rate by Agent" = No data.
- Ação: garantir pipeline de métricas FinOps (token/seat/total por engine/projeto/tenant) e tracing
  (token_burn, seat_seconds por agente) chegando ao Prometheus; validar labels usados nas queries.

## GRAF-05 (P2) — Tasks Completed = 0 e throughput por agente vazio
"Tasks Completed" e "Tasks Completed per Agent (rate)" zerados; gauges "Avg Task Duration per Agent"
todos 0s.
- Ação: emitir `herdmaster_agent_tasks_completed`/`avg_task_seconds` reais após ciclos de task; validar
  no painel após reconciliação do registro.

## GRAF-06 (P2) — Dashboards por agente/rota (TD7)
Expandir cobertura por agente e por rota; garantir provisionamento automático de todos os dashboards
e datasources em `HerdMaster/deploy/observability/grafana/`.
- Ação: revisar provisioning (dashboards + datasource Prometheus), versionar JSONs, confirmar
  auto-discovery (`updateIntervalSeconds`).

## GRAF-07 (P3) — Acesso estável ao Grafana a partir do Windows
- Ação: portproxy no Windows OU WSL mirrored networking OU publicar portas via bridge (sem quebrar o
  scrape host-network do Prometheus). Definir URL estável (DNS/host local).

## GRAF-08 (P3) — Segurança/hardening do Grafana
- Ação: trocar credencial admin default, definir org/datasource provisionados como código, restringir
  exposição de portas, habilitar auth conforme ambiente.

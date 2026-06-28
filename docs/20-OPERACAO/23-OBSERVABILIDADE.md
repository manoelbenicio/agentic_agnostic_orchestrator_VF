# 23 — Observabilidade

> **Onde vive o stack:** o `docker-compose.yml` da observabilidade fica em **`../HerdMaster/deploy/observability/`** (projeto irmão), referenciado por `OBS_DIR`/`OBS_COMPOSE` em `ops/common.sh`. A AOP **consome** essa stack; não a versiona. Esta página documenta o que a AOP espera dela (verificado em `common.sh`/`start.sh`).

## 1. Componentes e portas

| Serviço | Porta | Healthcheck usado pela AOP |
|---------|-------|----------------------------|
| Prometheus | 9090 | `GET /-/healthy` |
| Grafana | 3000 | `GET /api/health` |
| Alertmanager | 9093 | `GET /-/ready` |
| Blackbox exporter | 9115 | `GET /-/healthy` |
| Remediation webhook | 9099 | `GET /health` |

Origem: `ops/start.sh` (`wait_observability_http_200 ...`) e `ops/common.sh` (`print_status_table`).

`common.sh` detecta automaticamente se a stack usa `network_mode: host` ou portas publicadas (`observability_network_mode`), e loga o modo nos probes.

---

## 2. Fonte de métricas da AOP

### Control-plane — `GET /metrics` (porta 8090)

Em `app/main.py`, o endpoint `/metrics` retorna texto Prometheus com:

```
# HELP aop_control_plane_up Control plane liveness
# TYPE aop_control_plane_up gauge
aop_control_plane_up 1
<FinOpsMetricsExporter(...).project_metrics(tenant_id="tenant-a", project_id="project-a")>
<TracingMetricsExporter(...).burn_metrics()>
```

> ⚠️ **Limitação verificada:** o exporter FinOps em `/metrics` está **hardcoded** para `tenant_id="tenant-a"`/`project_id="project-a"`. Não é um exporter multi-tenant genérico ainda. Para FinOps real por tenant/projeto/modelo, ver o roadmap em [`30-COMPONENTES/35-FINOPS-E-CUSTOS.md`](../30-COMPONENTES/35-FINOPS-E-CUSTOS.md) e a pesquisa em [`90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md`](../90-DECISOES/92-PESQUISA-FERRAMENTAS-PREMIUM.md).

### HerdMaster — `GET /metrics` (porta 8080, autenticado)

Exige `Authorization: Bearer <token>`. O Prometheus autentica via `credentials_file` apontando para `/tmp/aop-ops-runtime/prometheus.token` (cópia `644` do token — ver [`10-DEPLOY/14-SEGREDOS-E-TOKENS.md`](../10-DEPLOY/14-SEGREDOS-E-TOKENS.md)).

---

## 3. Verificação

```bash
# Healthchecks da stack de observabilidade:
curl -s -o /dev/null -w 'prometheus   %{http_code}\n' http://127.0.0.1:9090/-/healthy
curl -s -o /dev/null -w 'grafana      %{http_code}\n' http://127.0.0.1:3000/api/health
curl -s -o /dev/null -w 'alertmanager %{http_code}\n' http://127.0.0.1:9093/-/ready
curl -s -o /dev/null -w 'blackbox     %{http_code}\n' http://127.0.0.1:9115/-/healthy
curl -s -o /dev/null -w 'remediation  %{http_code}\n' http://127.0.0.1:9099/health

# Métricas da AOP:
curl -s http://127.0.0.1:8090/metrics | head -20

# Métricas do HerdMaster (autenticado):
curl -s -H "Authorization: Bearer $(tr -d '\r\n' < /tmp/aop-ops-runtime/herdmaster.token)" \
  http://127.0.0.1:8080/metrics | head

# Prometheus está raspando os alvos?
curl -s 'http://127.0.0.1:9090/api/v1/targets' | python3 -m json.tool | grep -E 'health|scrapeUrl' | head
```

---

## 4. Dashboards e KPIs

Grafana (`:3000`) serve os dashboards. O provisionamento (datasources/dashboards) faz parte do compose de observabilidade do **HerdMaster** — confirme lá quais dashboards já existem.

KPIs-alvo do produto (visão; nem todos têm métrica-fonte hoje):
- **FinOps:** custo realtime por projeto/task/grupo-TL/grupo-agente/Kanban/modelo. → **lacuna**: hoje o `/metrics` só expõe um par tenant/projeto fixo. Roadmap em doc 35.
- **Burn de tokens:** `TracingMetricsExporter.burn_metrics()` já expõe burn agregado.
- **Liveness:** `aop_control_plane_up`.
- **Saúde de coupling:** derivável de `/health` (campo `coupling.status`).

---

## 5. Alertas e remediação

- **Alertmanager** (`:9093`) recebe alertas do Prometheus.
- **Remediation webhook** (`:9099`) é um receiver para automação de resposta (auto-remediação). As regras vivem no compose de observabilidade do HerdMaster.
- Regras ativas em `../HerdMaster/deploy/observability/prometheus/alert_rules.yml`:
  - integridade do registry HerdMaster: `UnlistedAgentsDetected`, `AgentCountMismatch`, `WhitelistComplianceViolation`;
  - saúde dos agentes e pipeline: `AgentUnhealthy`, `AllAgentsUnhealthy`, `TaskFailureRateHigh`, `HerdMasterDown`;
  - AOP control-plane: `AOPControlPlaneMetricsDown`, `AOPControlPlaneLivenessMissing`, `AOPFinOpsMetricsMissing`, `AOPTraceTokenBurnSpike`;
  - stack de observabilidade: `AlertmanagerDown`, `RemediationWebhookDown`, `BlackboxProbeExporterDown`, `CriticalHTTPProbeFailed`, `CriticalHTTPProbeSlow`.
- Receivers em `../HerdMaster/deploy/observability/alertmanager/alertmanager.yml`:
  - `default-log` para log geral;
  - `auto-remediation-webhook` para alertas `remediation="auto"` do registry;
  - `critical-log` para severidade crítica;
  - `observability-log` para degradação da própria stack de observabilidade.
- O job blackbox `herdmaster-e2e-api-monitor` cobre HerdMaster, AOP `/health`, AOP `/health/ready`, AOP `/metrics`, Alertmanager, Remediation e Blackbox exporter.

> Roadmap remanescente: adicionar métricas Prometheus explícitas para coupling degradado e falhas de `verify_dump` dos backups; hoje esses estados são verificáveis por `/health/ready`, blackbox e logs, mas ainda não têm séries Prometheus dedicadas.

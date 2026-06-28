"use client";

import React, { useEffect, useState } from "react";
import { 
  Gauge, 
  Activity, 
  AlertTriangle, 
  CheckCircle2, 
  XCircle, 
  ExternalLink, 
  RefreshCw, 
  Server, 
  Database, 
  Network
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type HealthCheckState = {
  status: string;
  checks: {
    postgres: boolean;
    redis: boolean;
  };
  coupling: {
    status: string;
    last_error: string | null;
    message_bus_status: string | null;
    message_bus_error: string | null;
  };
};

type AlertmanagerAlert = {
  annotations: {
    summary?: string;
    description?: string;
  };
  labels: {
    alertname: string;
    severity: string;
    component: string;
    [key: string]: string;
  };
  startsAt: string;
  status: {
    state: string;
  };
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";
const alertmanagerUrl = process.env.NEXT_PUBLIC_ALERTMANAGER_URL ?? "http://127.0.0.1:9093";
const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL ?? "http://127.0.0.1:3000";

// Static catalog of rules from alert_rules.yml to match firing alerts against
const ALERT_RULES_CATALOG = [
  {
    name: "UnlistedAgentsDetected",
    severity: "warning",
    component: "agent_registry",
    summary: "Agentes fantasmas detectados no DB",
    description: "O DB contém agentes não documentados na whitelist canônica. Auto-remediation disparada.",
    expr: "herdmaster_unlisted_agents_total > 0"
  },
  {
    name: "AgentCountMismatch",
    severity: "warning",
    component: "agent_registry",
    summary: "Contagem total diverge do esperado",
    description: "Contagem de agentes no DB diverge da whitelist canônica. DB atual != 7.",
    expr: "herdmaster_agents_total != herdmaster_agents_expected_total"
  },
  {
    name: "WhitelistComplianceViolation",
    severity: "critical",
    component: "agent_registry",
    summary: "Registry integrity VIOLADA",
    description: "Confirmado agentes fora da whitelist canônica. Pipeline de dispatch em risco.",
    expr: "herdmaster_whitelist_compliant == 0"
  },
  {
    name: "AgentUnhealthy",
    severity: "warning",
    component: "watchdog",
    summary: "Agente específico unhealthy",
    description: "O watchdog reporta saúde degradada para um agente específico por mais de 2 min.",
    expr: "herdmaster_agent_health == 0"
  },
  {
    name: "AllAgentsUnhealthy",
    severity: "critical",
    component: "watchdog",
    summary: "TODOS os agentes HerdMaster estão unhealthy",
    description: "Nenhum worker disponível para despacho de tarefas.",
    expr: "herdmaster_agents_healthy == 0"
  },
  {
    name: "TaskFailureRateHigh",
    severity: "warning",
    component: "dispatch",
    summary: "Tasks em estado failed no HerdMaster",
    description: "Taxa de falhas de tarefas elevada nos últimos 5 minutos.",
    expr: "herdmaster_tasks_total{state=\"failed\"} > 3"
  },
  {
    name: "HerdMasterDown",
    severity: "critical",
    component: "control_plane",
    summary: "HerdMaster Control Plane está DOWN",
    description: "O endpoint /metrics não responde. Executar: hm-start.",
    expr: "up{job=\"herdmaster-internal-metrics\"} == 0"
  },
  {
    name: "AOPControlPlaneMetricsDown",
    severity: "critical",
    component: "aop_control_plane",
    summary: "AOP Control Plane /metrics está DOWN",
    description: "Prometheus não consegue coletar as métricas do endpoint /metrics do AOP.",
    expr: "up{job=\"aop-control-plane-metrics\"} == 0"
  },
  {
    name: "AOPControlPlaneLivenessMissing",
    severity: "warning",
    component: "aop_control_plane",
    summary: "Métrica aop_control_plane_up ausente",
    description: "O scrape responde, mas a métrica de liveness do AOP não está presente.",
    expr: "absent(aop_control_plane_up)"
  },
  {
    name: "AOPFinOpsMetricsMissing",
    severity: "warning",
    component: "finops",
    summary: "Métricas FinOps do AOP ausentes",
    description: "aop_finops_project_cost_usd não foi exposta pelo control-plane.",
    expr: "absent(aop_finops_project_cost_usd)"
  },
  {
    name: "AOPTraceTokenBurnSpike",
    severity: "warning",
    component: "tracing",
    summary: "Token burn alto no AOP tracing",
    description: "O tracing registrou um consumo de mais de 10k tokens nos últimos 15 min.",
    expr: "sum(increase(aop_trace_token_burn_total[15m])) > 10000"
  }
];

export default function ObservabilityPage() {
  const [health, setHealth] = useState<HealthCheckState | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<AlertmanagerAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadObservabilityData() {
      setLoading(true);
      setError(null);
      try {
        const [healthRes, alertsRes] = await Promise.all([
          fetch(`${apiBase}/health/ready`).catch(() => null),
          fetch(`${alertmanagerUrl}/api/v2/alerts`).catch(() => null)
        ]);

        let healthData: HealthCheckState | null = null;
        if (healthRes && healthRes.ok) {
          healthData = (await healthRes.json()) as HealthCheckState;
        }

        let alertsData: AlertmanagerAlert[] = [];
        if (alertsRes && alertsRes.ok) {
          alertsData = (await alertsRes.json()) as AlertmanagerAlert[];
        }

        if (active) {
          setHealth(healthData);
          setActiveAlerts(alertsData);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadObservabilityData();
    return () => {
      active = false;
    };
  }, [refreshTrigger]);

  const stats = React.useMemo(() => {
    const isPostgresUp = health?.checks?.postgres ?? false;
    const isRedisUp = health?.checks?.redis ?? false;
    const isCouplingUp = health?.coupling?.status === "connected";
    const isBusUp = health?.coupling?.message_bus_status === "connected";

    return {
      isPostgresUp,
      isRedisUp,
      isCouplingUp,
      isBusUp,
      alertsCount: activeAlerts.length,
      criticalAlertsCount: activeAlerts.filter((a) => a.labels.severity === "critical").length
    };
  }, [health, activeAlerts]);

  return (
    <div className="space-y-6 aop-fade-in">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 inline-flex items-center gap-2 rounded-md border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            <Gauge className="size-3.5 text-accent animate-pulse" />
            Observability Panel
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Infrastructure & Integration Monitoring
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Real-time coupling checks, active alert states, and Grafana telemetry.
          </p>
        </div>
        <button
          onClick={() => setRefreshTrigger((prev) => prev + 1)}
          disabled={loading}
          className="flex h-10 items-center justify-center gap-2 rounded-lg border border-border bg-card px-4 text-sm font-medium text-foreground shadow-sm transition-all hover:bg-muted active:scale-95 disabled:opacity-55"
        >
          <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
          Recarregar dados
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive aop-float-in">
          <AlertTriangle className="size-5 shrink-0" />
          <div className="font-medium">{error}</div>
        </div>
      )}

      {/* Overview Status Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Postgres */}
        <Card className="hover:border-primary/50 transition-all duration-300">
          <CardContent className="pt-5 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                PostgreSQL
              </span>
              <span className="text-xl font-bold text-foreground">
                {stats.isPostgresUp ? "Healthy" : "Offline"}
              </span>
            </div>
            {stats.isPostgresUp ? (
              <Database className="size-8 text-success" />
            ) : (
              <Database className="size-8 text-destructive" />
            )}
          </CardContent>
        </Card>

        {/* Redis */}
        <Card className="hover:border-primary/50 transition-all duration-300">
          <CardContent className="pt-5 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                Redis Cache
              </span>
              <span className="text-xl font-bold text-foreground">
                {stats.isRedisUp ? "Healthy" : "Offline"}
              </span>
            </div>
            {stats.isRedisUp ? (
              <Server className="size-8 text-success" />
            ) : (
              <Server className="size-8 text-destructive" />
            )}
          </CardContent>
        </Card>

        {/* HerdMaster Coupling */}
        <Card className="hover:border-primary/50 transition-all duration-300">
          <CardContent className="pt-5 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                Coupling Status
              </span>
              <span className="text-xl font-bold text-foreground">
                {health?.coupling?.status || "disconnected"}
              </span>
            </div>
            {stats.isCouplingUp ? (
              <Network className="size-8 text-success" />
            ) : (
              <Network className="size-8 text-destructive animate-pulse" />
            )}
          </CardContent>
        </Card>

        {/* Active Alerts */}
        <Card className="hover:border-primary/50 transition-all duration-300">
          <CardContent className="pt-5 flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                Alertas Ativos
              </span>
              <span className="text-xl font-bold text-foreground">
                {stats.alertsCount} firing
              </span>
            </div>
            {stats.alertsCount > 0 ? (
              <AlertTriangle className={`size-8 ${stats.criticalAlertsCount > 0 ? "text-destructive" : "text-warning"} animate-bounce`} />
            ) : (
              <CheckCircle2 className="size-8 text-success" />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Grafana Links & coupling Log */}
      <div className="grid gap-6 md:grid-cols-3">
        {/* Grafana Dashboards Links */}
        <Card className="md:col-span-1">
          <CardHeader>
            <CardTitle>Grafana Dashboards</CardTitle>
            <CardDescription>Visualizações e painéis de telemetria avançados.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <a 
              href={`${grafanaUrl}/d/aop-finops-tracing/aop-finops-and-tracing`}
              target="_blank" 
              rel="noopener noreferrer" 
              className="flex items-center justify-between p-3.5 rounded-lg border border-border bg-card hover:border-primary/50 hover:bg-muted/30 transition-all duration-200 group"
            >
              <div className="flex flex-col">
                <span className="text-sm font-semibold text-foreground group-hover:text-accent">
                  AOP FinOps & Tracing
                </span>
                <span className="text-xs text-muted-foreground">Tokens burn, Seat costs & metrics</span>
              </div>
              <ExternalLink className="size-4 text-muted-foreground group-hover:text-accent" />
            </a>

            <a 
              href={`${grafanaUrl}/d/herdmaster-squad-control/herdmaster-squad-control`}
              target="_blank" 
              rel="noopener noreferrer" 
              className="flex items-center justify-between p-3.5 rounded-lg border border-border bg-card hover:border-primary/50 hover:bg-muted/30 transition-all duration-200 group"
            >
              <div className="flex flex-col">
                <span className="text-sm font-semibold text-foreground group-hover:text-accent">
                  HerdMaster Squad Control
                </span>
                <span className="text-xs text-muted-foreground">Squad nodes, status & health</span>
              </div>
              <ExternalLink className="size-4 text-muted-foreground group-hover:text-accent" />
            </a>

            <div className="pt-2 text-xs text-muted-foreground">
              * O painel local do Grafana está disponível em:{" "}
              <a href={grafanaUrl} target="_blank" rel="noreferrer" className="text-accent underline">
                {grafanaUrl}
              </a>
            </div>
          </CardContent>
        </Card>

        {/* Integration coupling logs */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Estado do Coupling (AOP ↔ HerdMaster)</CardTitle>
            <CardDescription>Rastreabilidade da comunicação e sincronização do barramento.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="p-4 rounded-lg border border-border bg-background/50">
                <div className="text-xs text-muted-foreground font-medium uppercase">Barramento de Mensagens</div>
                <div className="mt-1 flex items-center gap-2">
                  <span className={`size-2 rounded-full ${stats.isBusUp ? "bg-success" : "bg-destructive"}`} />
                  <span className="text-sm font-semibold">{health?.coupling?.message_bus_status || "unknown"}</span>
                </div>
                {health?.coupling?.message_bus_error && (
                  <div className="mt-2 text-xs text-destructive font-mono bg-destructive/5 p-2 rounded">
                    {health?.coupling?.message_bus_error}
                  </div>
                )}
              </div>

              <div className="p-4 rounded-lg border border-border bg-background/50">
                <div className="text-xs text-muted-foreground font-medium uppercase">Último erro de acoplamento</div>
                <div className="mt-1 text-sm font-semibold truncate">
                  {health?.coupling?.last_error ? (
                    <span className="text-destructive font-mono text-xs">{health.coupling.last_error}</span>
                  ) : (
                    <span className="text-success">Sem falhas registradas</span>
                  )}
                </div>
              </div>
            </div>

            <div className="text-xs text-muted-foreground border-t border-border pt-4">
              Liveness Check: <span className="font-semibold text-foreground font-mono">{health?.status || "offline"}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Alert Manager alerts Monitoring */}
      <Card>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <CardTitle>Central de Monitoramento e Alertas</CardTitle>
            <CardDescription>
              Lista completa de regras de alerta do Prometheus e seu estado de ativação atual.
            </CardDescription>
          </div>
          <Badge variant={stats.alertsCount > 0 ? "destructive" : "success"} className="h-6">
            {stats.alertsCount > 0 ? `${stats.alertsCount} ALERTAS DISPARANDO` : "SISTEMA SEGURO"}
          </Badge>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {ALERT_RULES_CATALOG.map((rule) => {
              const activeInstance = activeAlerts.find((a) => a.labels.alertname === rule.name);
              const isFiring = !!activeInstance;

              return (
                <div 
                  key={rule.name}
                  className={`flex flex-col md:flex-row md:items-center justify-between p-4 rounded-lg border transition-all duration-300 ${
                    isFiring 
                      ? "border-destructive bg-destructive/10 shadow-md shadow-destructive/5" 
                      : "border-border bg-card/60 hover:bg-muted/10"
                  }`}
                >
                  <div className="space-y-1 max-w-2xl">
                    <div className="flex items-center gap-2.5">
                      <span className="font-semibold text-foreground">{rule.name}</span>
                      <Badge variant={rule.severity === "critical" ? "destructive" : "warning"}>
                        {rule.severity.toUpperCase()}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground uppercase bg-muted px-1.5 py-0.5 rounded">
                        {rule.component}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground font-mono bg-background/50 p-1.5 rounded inline-block max-w-full overflow-x-auto">
                      expr: {rule.expr}
                    </p>
                    <p className="text-sm text-foreground mt-1">{rule.description}</p>
                    {isFiring && activeInstance?.annotations?.description && (
                      <p className="text-xs font-semibold text-destructive mt-1 bg-destructive/5 p-2 rounded border border-destructive/20">
                        {activeInstance.annotations.description}
                      </p>
                    )}
                  </div>
                  
                  <div className="mt-4 md:mt-0 flex items-center gap-2">
                    {isFiring ? (
                      <div className="flex items-center gap-1.5 text-xs font-bold text-destructive animate-pulse bg-destructive/10 px-3 py-1.5 rounded-full border border-destructive/20">
                        <XCircle className="size-4" />
                        FIRING
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-success bg-success/10 px-3 py-1.5 rounded-full border border-success/20">
                        <CheckCircle2 className="size-4" />
                        RESOLVED
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

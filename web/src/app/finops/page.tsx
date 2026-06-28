"use client";

import React, { useEffect, useState, useMemo } from "react";
import { 
  CircleDollarSign, 
  Coins, 
  UserX, 
  Server, 
  TrendingUp, 
  AlertCircle, 
  RefreshCw,
  FolderDot
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type Project = {
  project_id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  status: string;
  metadata: Record<string, any>;
};

type Seat = {
  seat_id: string;
  tenant_id: string;
  vendor: string;
  leased: boolean;
  ref_count: number;
};

type ProjectRollup = {
  tenant_id: string;
  project_id: string;
  total_cost_usd: string;
  token_cost_usd: string;
  seat_cost_usd: string;
  record_count: number;
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

export default function FinOpsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [seats, setSeats] = useState<Seat[]>([]);
  const [rollups, setRollups] = useState<Record<string, ProjectRollup>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        // Fetch projects and seats in parallel
        const [projRes, seatsRes] = await Promise.all([
          fetch(`${apiBase}/projects`),
          fetch(`${apiBase}/seats`)
        ]);

        if (!projRes.ok) throw new Error(`GET /projects returned ${projRes.status}`);
        if (!seatsRes.ok) throw new Error(`GET /seats returned ${seatsRes.status}`);

        const projData = (await projRes.json()) as Project[];
        const seatsData = (await seatsRes.json()) as { seats: Seat[] } | Seat[];
        
        const finalSeats = Array.isArray(seatsData) 
          ? seatsData 
          : (seatsData.seats || []);

        if (active) {
          setProjects(projData);
          setSeats(finalSeats);
        }

        // Fetch rollup for each project in parallel
        const rollupPromises = projData.map(async (p) => {
          try {
            const res = await fetch(`${apiBase}/finops/projects/${p.tenant_id}/${p.project_id}/rollup`);
            if (res.ok) {
              const data = (await res.json()) as ProjectRollup;
              return { project_id: p.project_id, rollup: data };
            }
          } catch (e) {
            console.error(`Failed to fetch rollup for project ${p.project_id}`, e);
          }
          return { project_id: p.project_id, rollup: null };
        });

        const rollupResults = await Promise.all(rollupPromises);
        
        if (active) {
          const rollupMap: Record<string, ProjectRollup> = {};
          rollupResults.forEach(({ project_id, rollup }) => {
            if (rollup) {
              rollupMap[project_id] = rollup;
            }
          });
          setRollups(rollupMap);
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

    loadData();
    return () => {
      active = false;
    };
  }, [refreshTrigger]);

  // Derived metrics
  const totalCost = useMemo(() => {
    return Object.values(rollups).reduce((sum, r) => sum + parseFloat(r.total_cost_usd), 0);
  }, [rollups]);

  const totalTokenCost = useMemo(() => {
    return Object.values(rollups).reduce((sum, r) => sum + parseFloat(r.token_cost_usd), 0);
  }, [rollups]);

  const totalSeatCost = useMemo(() => {
    return Object.values(rollups).reduce((sum, r) => sum + parseFloat(r.seat_cost_usd), 0);
  }, [rollups]);

  const idleSeats = useMemo(() => {
    return seats.filter((s) => !s.leased || s.ref_count === 0);
  }, [seats]);

  const activeSeatsCount = seats.length - idleSeats.length;

  const tokenPercentage = useMemo(() => {
    if (totalCost === 0) return 50;
    return Math.round((totalTokenCost / totalCost) * 100);
  }, [totalCost, totalTokenCost]);

  const seatPercentage = 100 - tokenPercentage;

  return (
    <div className="space-y-6 aop-fade-in">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 inline-flex items-center gap-2 rounded-md border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            <Coins className="size-3.5 text-accent animate-pulse" />
            FinOps Management
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Attribution & Resource Allocation
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Real-time project rollups, token-to-seat cost metrics, and seat optimization.
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
          <AlertCircle className="size-5 shrink-0" />
          <div className="font-medium">{error}</div>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="hover:border-primary/50 transition-all duration-300 hover:-translate-y-1">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Custo Total
            </CardTitle>
            <CircleDollarSign className="size-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight text-foreground">
              ${totalCost.toFixed(2)}
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="font-semibold text-accent">${totalTokenCost.toFixed(2)}</span> tokens
              <span>•</span>
              <span className="font-semibold text-teal-400">${totalSeatCost.toFixed(2)}</span> seats
            </div>
          </CardContent>
        </Card>

        <Card className="hover:border-primary/50 transition-all duration-300 hover:-translate-y-1">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Seats Ativos
            </CardTitle>
            <Server className="size-4 text-success" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight text-foreground">
              {activeSeatsCount} <span className="text-lg font-normal text-muted-foreground">/ {seats.length}</span>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {seats.length > 0 
                ? `${Math.round((activeSeatsCount / seats.length) * 100)}% de ocupação dos recursos`
                : "Nenhum seat provisionado"}
            </div>
          </CardContent>
        </Card>

        <Card className="hover:border-primary/50 transition-all duration-300 hover:-translate-y-1">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Seats Ociosos
            </CardTitle>
            <UserX className="size-4 text-warning" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight text-foreground">
              {idleSeats.length}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {seats.length > 0 
                ? `${Math.round((idleSeats.length / seats.length) * 100)}% de desperdício em seats`
                : "Recursos sem desperdício"}
            </div>
          </CardContent>
        </Card>

        <Card className="hover:border-primary/50 transition-all duration-300 hover:-translate-y-1">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Projetos Atribuídos
            </CardTitle>
            <FolderDot className="size-4 text-teal" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight text-foreground">
              {projects.length}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              {projects.filter((p) => p.status === "active").length} projetos ativos no momento
            </div>
          </CardContent>
        </Card>
      </div>

      {/* cost distribution and Gauges */}
      <div className="grid gap-6 md:grid-cols-3">
        {/* Cost Distribution card */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Distribuição de Custos</CardTitle>
            <CardDescription>
              Comparativo percentual de consumo entre APIs (Tokens) e infraestrutura (Seats).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Visual Gauge */}
            <div className="flex flex-col items-center justify-center py-6">
              <div className="relative flex size-40 items-center justify-center rounded-full border-8 border-secondary bg-transparent">
                {/* Simulated circle stroke using clip/conic-gradient */}
                <div 
                  className="absolute inset-0 -m-2 rounded-full border-8"
                  style={{
                    borderColor: "#00B0BD", // Accent
                    clipPath: `polygon(50% 50%, 50% 0%, ${tokenPercentage >= 25 ? "100% 0%," : ""} ${tokenPercentage >= 50 ? "100% 100%," : ""} ${tokenPercentage >= 75 ? "0% 100%," : ""} ${tokenPercentage >= 100 ? "0% 0%," : ""} 50% 0%)`,
                    transform: "rotate(-90deg)"
                  }}
                />
                <div className="z-10 text-center">
                  <div className="text-sm font-semibold text-muted-foreground">Tokens</div>
                  <div className="text-3xl font-extrabold text-foreground">{tokenPercentage}%</div>
                </div>
              </div>
              
              <div className="mt-6 flex w-full max-w-sm items-center justify-around text-sm">
                <div className="flex items-center gap-2">
                  <span className="size-3 rounded-full bg-[#00B0BD]" />
                  <span>Tokens (${totalTokenCost.toFixed(2)})</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="size-3 rounded-full bg-secondary" />
                  <span>Seats (${totalSeatCost.toFixed(2)})</span>
                </div>
              </div>
            </div>

            {/* Cost Progress breakdown */}
            <div className="space-y-4">
              <div>
                <div className="mb-1 flex items-center justify-between text-sm font-medium">
                  <span className="text-muted-foreground">Token Consumption</span>
                  <span className="text-foreground">{tokenPercentage}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div 
                    className="h-full bg-accent rounded-full transition-all duration-1000"
                    style={{ width: `${tokenPercentage}%` }}
                  />
                </div>
              </div>
              
              <div>
                <div className="mb-1 flex items-center justify-between text-sm font-medium">
                  <span className="text-muted-foreground">Seat Allocations</span>
                  <span className="text-foreground">{seatPercentage}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div 
                    className="h-full bg-teal-400 rounded-full transition-all duration-1000"
                    style={{ width: `${seatPercentage}%` }}
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Efficiency Card / Idle seat list */}
        <Card className="flex flex-col justify-between">
          <CardHeader>
            <CardTitle>Recursos Ociosos</CardTitle>
            <CardDescription>
              Detalhamento de Seats ativos que não possuem alocação ou uso ativo.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex-1 space-y-4">
            {idleSeats.length === 0 ? (
              <div className="flex h-44 flex-col items-center justify-center text-center">
                <TrendingUp className="mb-2 size-8 text-success animate-bounce" />
                <p className="text-sm font-medium text-foreground">100% de Eficiência</p>
                <p className="text-xs text-muted-foreground mt-1">Todos os seats provisionados estão leased e ativos.</p>
              </div>
            ) : (
              <div className="max-h-64 overflow-y-auto space-y-2">
                {idleSeats.map((s) => (
                  <div 
                    key={s.seat_id} 
                    className="flex items-center justify-between p-3 rounded-lg border border-border bg-background/50 hover:bg-muted/30 transition-all duration-200"
                  >
                    <div>
                      <div className="text-sm font-semibold text-foreground">{s.seat_id}</div>
                      <div className="text-[10px] text-muted-foreground uppercase">{s.vendor}</div>
                    </div>
                    <Badge variant="warning">
                      OCIOSO
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
          <div className="p-5 pt-0 border-t border-border mt-auto">
            <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
              <span>Custo potencial desperdiçado:</span>
              <span className="font-semibold text-warning">${(idleSeats.length * 12.5).toFixed(2)} / mês</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Project Rollups */}
      <Card>
        <CardHeader>
          <CardTitle>Rollup de Custos por Projeto</CardTitle>
          <CardDescription>
            Análise detalhada de custos acumulados (Seat + Tokens) por projeto ativo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <FolderDot className="mb-2 size-8 opacity-40" />
              <p className="text-sm">Nenhum projeto encontrado</p>
              <p className="text-xs opacity-60 mt-1">Crie um projeto na aba Projetos para iniciar o rastreamento.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-border text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <th className="py-3 px-4">Projeto</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Custo Token</th>
                    <th className="py-3 px-4 text-right">Custo Seat</th>
                    <th className="py-3 px-4 text-right">Total Acumulado</th>
                    <th className="py-3 px-4 text-right">Registros</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {projects.map((p) => {
                    const rollup = rollups[p.project_id];
                    const projTotal = rollup ? parseFloat(rollup.total_cost_usd) : 0;
                    const projToken = rollup ? parseFloat(rollup.token_cost_usd) : 0;
                    const projSeat = rollup ? parseFloat(rollup.seat_cost_usd) : 0;

                    return (
                      <tr 
                        key={p.project_id} 
                        className="hover:bg-muted/20 transition-colors duration-150 group"
                      >
                        <td className="py-3 px-4">
                          <div className="font-semibold text-foreground">{p.name}</div>
                          {p.description && (
                            <div className="text-xs text-muted-foreground mt-0.5 max-w-sm truncate">
                              {p.description}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant={p.status === "active" ? "success" : "secondary"}>
                            {p.status}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">
                          ${projToken.toFixed(4)}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">
                          ${projSeat.toFixed(4)}
                        </td>
                        <td className="py-3 px-4 text-right font-semibold text-foreground font-mono">
                          ${projTotal.toFixed(4)}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs text-muted-foreground">
                          {rollup ? rollup.record_count : 0}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

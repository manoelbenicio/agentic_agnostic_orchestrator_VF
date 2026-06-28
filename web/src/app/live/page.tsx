"use client";

import React, { useState, useEffect, useMemo } from "react";
import { 
  Radio, 
  Brain, 
  Loader2, 
  Terminal, 
  Search, 
  Trash2, 
  Play, 
  Pause, 
  Download,
  Server,
  Zap,
  Activity,
  Maximize2,
  ChevronRight
} from "lucide-react";
import { useAgents } from "@/lib/hooks";
import { LiveTracePanel } from "@/components/live/LiveTracePanel";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

// Let's create an enhanced live page
export default function LivePage() {
  const { agents, loading, error } = useAgents();
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [selectedRuntimeIds, setSelectedRuntimeIds] = useState<string[]>([]);
  const [customRuntimeId, setCustomRuntimeId] = useState("");
  const [activeTab, setActiveTab] = useState<"agents" | "runtimes">("agents");

  // Extract unique runtimes from agents if any
  const agentRuntimes = useMemo(() => {
    const runtimesSet = new Set<string>();
    agents.forEach((a) => {
      if (a.pane_id) runtimesSet.add(a.pane_id);
    });
    // Add default runtimes
    runtimesSet.add("runtime-local");
    return Array.from(runtimesSet);
  }, [agents]);

  function toggleAgent(agentId: string) {
    setSelectedAgentIds((prev) =>
      prev.includes(agentId)
        ? prev.filter((id) => id !== agentId)
        : [...prev, agentId]
    );
  }

  function toggleRuntime(runtimeId: string) {
    setSelectedRuntimeIds((prev) =>
      prev.includes(runtimeId)
        ? prev.filter((id) => id !== runtimeId)
        : [...prev, runtimeId]
    );
  }

  function addCustomRuntime(e: React.FormEvent) {
    e.preventDefault();
    if (!customRuntimeId.trim()) return;
    const trimmed = customRuntimeId.trim();
    if (!selectedRuntimeIds.includes(trimmed)) {
      setSelectedRuntimeIds((prev) => [...prev, trimmed]);
    }
    setCustomRuntimeId("");
  }

  return (
    <div className="space-y-6 aop-fade-in">
      {/* Page Header */}
      <div>
        <div className="mb-1 inline-flex items-center gap-2 rounded-md border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
          <Radio className="size-3.5 animate-pulse text-success" />
          Live Telemetry & Tracing
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Real-Time Trace Terminal
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Stream chain-of-thought steps, LLM calls, tool execution, and token burns directly from runtimes via WebSockets.
        </p>
      </div>

      {/* Controller / Selector Panel */}
      <Card className="border-border/60 shadow-md">
        <CardHeader className="pb-3 border-b border-border/40">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold tracking-wide uppercase text-muted-foreground">
              Monitor Targets
            </CardTitle>
            <div className="flex rounded-md bg-muted p-1 text-xs font-medium">
              <button
                onClick={() => setActiveTab("agents")}
                className={`rounded px-2 py-1 transition-all ${
                  activeTab === "agents"
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Agentes
              </button>
              <button
                onClick={() => setActiveTab("runtimes")}
                className={`rounded px-2 py-1 transition-all ${
                  activeTab === "runtimes"
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Runtimes
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {activeTab === "agents" ? (
            <div>
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                  <Loader2 className="size-4 animate-spin text-accent" />
                  Carregando agentes do registry...
                </div>
              ) : error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : agents.length === 0 ? (
                <div className="text-center py-6 border border-dashed border-border rounded-lg bg-background/50">
                  <Brain className="mx-auto size-8 text-muted-foreground/30 mb-2" />
                  <p className="text-sm text-muted-foreground font-medium">Nenhum agente ativo</p>
                  <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
                    O control-plane não possui agentes registrados no momento. Inicie um worker para transmitir eventos.
                  </p>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {agents.map((agent) => {
                    const active = selectedAgentIds.includes(agent.agent_id);
                    return (
                      <button
                        key={agent.agent_id}
                        onClick={() => toggleAgent(agent.agent_id)}
                        className={`flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm transition-all duration-200 active:scale-95 ${
                          active
                            ? "border-primary bg-primary/10 text-primary shadow-sm ring-1 ring-primary"
                            : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
                        }`}
                      >
                        <Brain className="size-4" />
                        <span className="font-semibold">{agent.label}</span>
                        <Badge variant="outline" className="text-[10px] uppercase">
                          {agent.vendor}
                        </Badge>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Custom Runtime Input */}
              <form onSubmit={addCustomRuntime} className="flex gap-2 max-w-md">
                <input
                  type="text"
                  placeholder="Nome do runtime (ex: runtime-local)"
                  value={customRuntimeId}
                  onChange={(e) => setCustomRuntimeId(e.target.value)}
                  className="flex-1 rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
                />
                <button
                  type="submit"
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/95 transition-all"
                >
                  Adicionar
                </button>
              </form>

              {/* Runtimes list */}
              <div className="flex flex-wrap gap-2">
                {agentRuntimes.map((rt) => {
                  const active = selectedRuntimeIds.includes(rt);
                  return (
                    <button
                      key={rt}
                      onClick={() => toggleRuntime(rt)}
                      className={`flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm transition-all duration-200 active:scale-95 ${
                        active
                          ? "border-accent bg-accent/15 text-accent shadow-sm ring-1 ring-accent"
                          : "border-border bg-card text-muted-foreground hover:border-accent/40 hover:bg-accent/5 hover:text-foreground"
                      }`}
                    >
                      <Server className="size-4" />
                      <span className="font-semibold">{rt}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stream Panels Grid */}
      {selectedAgentIds.length === 0 && selectedRuntimeIds.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card/40 p-16 text-center shadow-inner aop-float-in">
          <Terminal className="mx-auto mb-4 size-12 text-muted-foreground/30" />
          <h3 className="text-lg font-bold text-foreground">Nenhum canal ativo</h3>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            Selecione agentes ou runtimes acima para abrir os terminais de monitoramento em tempo real.
          </p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-1">
          {activeTab === "agents" ? (
            selectedAgentIds.map((agentId) => {
              const agent = agents.find((a) => a.agent_id === agentId);
              return (
                <LiveTracePanel
                  key={agentId}
                  agentId={agentId}
                  agentLabel={agent?.label}
                />
              );
            })
          ) : (
            selectedRuntimeIds.map((runtimeId) => (
              <RuntimeTracePanel key={runtimeId} runtimeId={runtimeId} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// Custom Trace Panel for Runtimes (polling fallback)
function RuntimeTracePanel({ runtimeId }: { runtimeId: string }) {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let active = true;
    if (paused) return;

    async function loadRuntimeTrace() {
      try {
        const res = await fetch(`${apiBase}/tracing/runtimes/${encodeURIComponent(runtimeId)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (active) {
          setEvents(data);
          setError(null);
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

    loadRuntimeTrace();
    const interval = setInterval(loadRuntimeTrace, 4000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [runtimeId, paused, refreshTrigger]);

  const totalBurn = useMemo(() => {
    return events.reduce((sum, e) => sum + (e.token_burn || 0), 0);
  }, [events]);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-lg aop-float-in">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-gradient-to-r from-card to-accent/5 px-4 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
            <Server className="size-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-foreground">{runtimeId}</div>
            <div className="text-[10px] text-muted-foreground uppercase flex items-center gap-1.5 mt-0.5">
              <span className="size-1.5 rounded-full bg-accent animate-pulse" />
              HTTP polling (4s) • {events.length} logs
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {totalBurn > 0 && (
            <div className="flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400 font-mono">
              <Zap className="size-3.5" />
              {totalBurn} tok
            </div>
          )}
          
          <button
            onClick={() => setPaused(!paused)}
            className="flex items-center justify-center size-8 rounded-lg border border-border bg-card hover:bg-muted transition-all"
            title={paused ? "Retomar logs" : "Pausar logs"}
          >
            {paused ? <Play className="size-4" /> : <Pause className="size-4" />}
          </button>

          <button
            onClick={() => setEvents([])}
            className="flex items-center justify-center size-8 rounded-lg border border-border bg-card hover:bg-muted text-destructive transition-all"
            title="Limpar log"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>

      {/* Console output */}
      <div className="bg-black/90 p-4 font-mono text-xs text-green-400 min-h-[16rem] max-h-[24rem] overflow-y-auto space-y-2">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground font-sans">
            <Activity className="size-8 opacity-30 mb-2 animate-pulse" />
            <p>Nenhum log de execução encontrado para este runtime.</p>
            <p className="text-[10px] opacity-60">Aguardando atividade...</p>
          </div>
        ) : (
          events.map((e, index) => {
            const signalColor = e.signal_type === "error" 
              ? "text-red-400" 
              : e.signal_type === "complete" 
                ? "text-cyan-400"
                : e.layer === "llm" 
                  ? "text-purple-400" 
                  : "text-green-400";

            return (
              <div key={`${e.event_id}-${index}`} className="flex items-start gap-2 hover:bg-white/5 p-1 rounded transition-all">
                <ChevronRight className="size-3.5 shrink-0 mt-0.5 text-muted-foreground" />
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-muted-foreground font-semibold">[{e.layer.toUpperCase()}]</span>
                    <span className={`${signalColor} font-bold`}>{e.signal_type.toUpperCase()}</span>
                    {e.token_burn > 0 && <span className="text-amber-400">🔥 {e.token_burn} tokens</span>}
                  </div>
                  <p className="text-foreground mt-0.5 break-words">{e.message}</p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

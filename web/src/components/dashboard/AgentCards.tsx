"use client";

import { useAgents } from "@/lib/hooks";
import { Activity, Bot, Server, Wifi, WifiOff } from "lucide-react";

const vendorColors: Record<string, string> = {
  openai: "from-emerald-500/20 to-teal-500/20 border-emerald-500/30",
  anthropic: "from-amber-500/20 to-orange-500/20 border-amber-500/30",
  google: "from-blue-500/20 to-indigo-500/20 border-blue-500/30",
  meta: "from-purple-500/20 to-violet-500/20 border-purple-500/30",
};

const statusDot: Record<string, string> = {
  active: "bg-success animate-pulse",
  idle: "bg-muted-foreground",
  offline: "bg-destructive",
};

function getVendorClass(vendor: string) {
  const key = vendor.toLowerCase();
  for (const [k, v] of Object.entries(vendorColors)) {
    if (key.includes(k)) return v;
  }
  return "from-primary/10 to-primary/20 border-primary/20";
}

export function AgentCards() {
  const { agents, loading, error, refetch } = useAgents();

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-40 animate-pulse rounded-lg border border-border bg-card"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
        <WifiOff className="mx-auto mb-2 size-8 text-destructive" />
        <p className="text-sm font-medium text-destructive">
          Failed to load agents
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        <button
          onClick={refetch}
          className="mt-3 rounded-md bg-destructive/10 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/20"
        >
          Retry
        </button>
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <Bot className="mx-auto mb-3 size-10 text-muted-foreground/50" />
        <p className="text-sm font-medium text-foreground">No agents registered</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Agents will appear here once they register with the control-plane.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">
          Agent Registry
          <span className="ml-2 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            {agents.length}
          </span>
        </h2>
        <button
          onClick={refetch}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="Refresh agents"
        >
          <Activity className="size-4" />
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <div
            key={agent.agent_id}
            className={`group relative overflow-hidden rounded-lg border bg-gradient-to-br p-4 shadow-sm transition-all hover:shadow-md ${getVendorClass(agent.vendor)}`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex size-9 items-center justify-center rounded-md bg-background/60 backdrop-blur">
                  <Server className="size-4 text-foreground" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">
                    {agent.label}
                  </div>
                  <div className="text-xs text-muted-foreground">{agent.role}</div>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <span
                  className={`size-2 rounded-full ${statusDot[agent.status] || statusDot.idle}`}
                />
                <span className="text-xs text-muted-foreground capitalize">
                  {agent.status}
                </span>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-background/60 px-2 py-0.5 text-[10px] font-medium text-foreground backdrop-blur">
                {agent.vendor}
              </span>
              {agent.stable_key && (
                <span className="rounded-full bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground backdrop-blur">
                  {agent.stable_key}
                </span>
              )}
            </div>
            <div className="mt-2 font-mono text-[10px] text-muted-foreground/70">
              {agent.agent_id.slice(0, 12)}…
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

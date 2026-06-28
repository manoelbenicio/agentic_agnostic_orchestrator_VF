"use client";

import { useProjectRollup } from "@/lib/hooks";
import { CircleDollarSign, TrendingUp, WifiOff } from "lucide-react";

interface FinOpsPanelProps {
  tenantId?: string;
  projectId?: string;
}

export function FinOpsPanel({
  tenantId = "tenant-a",
  projectId = "project-a",
}: FinOpsPanelProps) {
  const { rollup, loading, error, refetch } = useProjectRollup(tenantId, projectId);

  if (loading) {
    return (
      <div className="h-48 animate-pulse rounded-lg border border-border bg-card" />
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
        <WifiOff className="mx-auto mb-2 size-6 text-destructive" />
        <p className="text-sm font-medium text-destructive">FinOps unavailable</p>
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

  if (!rollup) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <CircleDollarSign className="mx-auto mb-3 size-10 text-muted-foreground/50" />
        <p className="text-sm font-medium text-foreground">No cost data yet</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Cost records appear after tasks execute and consume tokens or seats.
        </p>
      </div>
    );
  }

  const costItems = [
    {
      label: "Total Cost",
      value: `$${parseFloat(rollup.total_cost_usd).toFixed(4)}`,
      accent: true,
    },
    {
      label: "Token Cost",
      value: `$${parseFloat(rollup.token_cost_usd).toFixed(4)}`,
    },
    {
      label: "Seat Cost",
      value: `$${parseFloat(rollup.seat_cost_usd).toFixed(4)}`,
    },
    {
      label: "Records",
      value: rollup.record_count.toString(),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">
          FinOps
          <span className="ml-2 rounded-full bg-accent/30 px-2 py-0.5 text-xs font-medium text-accent-foreground">
            {tenantId}/{projectId}
          </span>
        </h2>
        <button
          onClick={refetch}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="Refresh FinOps data"
        >
          <TrendingUp className="size-4" />
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {costItems.map((item) => (
          <div
            key={item.label}
            className={`rounded-lg border p-4 shadow-sm ${
              item.accent
                ? "border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10"
                : "border-border bg-card"
            }`}
          >
            <div className="text-xs text-muted-foreground">{item.label}</div>
            <div
              className={`mt-2 text-xl font-semibold tabular-nums ${
                item.accent ? "text-primary" : "text-foreground"
              }`}
            >
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

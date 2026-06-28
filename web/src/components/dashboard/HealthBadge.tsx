"use client";

import { useHealth } from "@/lib/hooks";
import { CheckCircle, RefreshCw, XCircle } from "lucide-react";

export function HealthBadge() {
  const { data, loading, error, refetch } = useHealth();

  return (
    <button
      onClick={refetch}
      className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-accent/50"
      title={
        loading
          ? "Checking…"
          : error
            ? `Error: ${error}`
            : `Control-plane: ${data?.status ?? "unknown"}`
      }
    >
      {loading ? (
        <RefreshCw className="size-3.5 animate-spin text-muted-foreground" />
      ) : error ? (
        <XCircle className="size-3.5 text-destructive" />
      ) : (
        <CheckCircle className="size-3.5 text-success" />
      )}
      <span>
        {loading
          ? "Checking…"
          : error
            ? "API offline"
            : `API ${data?.status ?? "ok"}`}
      </span>
    </button>
  );
}

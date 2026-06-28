"use client";

import { useSeats } from "@/lib/hooks";
import { Activity, HardDrive, Wifi, WifiOff } from "lucide-react";

export function SeatCards() {
  const { seats, loading, error, refetch } = useSeats();

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-border bg-card"
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
          Failed to load seats
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

  if (seats.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <HardDrive className="mx-auto mb-3 size-10 text-muted-foreground/50" />
        <p className="text-sm font-medium text-foreground">No seats provisioned</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Runtime seats appear here once allocated by the orchestrator.
        </p>
      </div>
    );
  }

  const leasedCount = seats.filter((s) => s.leased).length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">
          Seat Pool
          <span className="ml-2 rounded-full bg-accent/30 px-2 py-0.5 text-xs font-medium text-accent-foreground">
            {leasedCount}/{seats.length} leased
          </span>
        </h2>
        <button
          onClick={refetch}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="Refresh seats"
        >
          <Activity className="size-4" />
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {seats.map((seat) => (
          <div
            key={seat.seat_id}
            className={`rounded-lg border p-4 shadow-sm transition-all hover:shadow-md ${
              seat.leased
                ? "border-success/30 bg-success/5"
                : "border-border bg-card"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HardDrive className="size-4 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">
                  {seat.vendor}
                </span>
              </div>
              {seat.leased ? (
                <Wifi className="size-4 text-success" />
              ) : (
                <WifiOff className="size-4 text-muted-foreground/50" />
              )}
            </div>
            <div className="mt-2 font-mono text-[10px] text-muted-foreground">
              {seat.seat_id.slice(0, 16)}…
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <span
                className={`size-1.5 rounded-full ${
                  seat.leased ? "bg-success" : "bg-muted-foreground/40"
                }`}
              />
              {seat.leased ? `${seat.ref_count} ref(s)` : "available"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

"use client";

import { Activity, CircleDollarSign, Server, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api-client";
import type { Agent, ProjectRollup as FinOpsRollup, Seat } from "@/lib/api-types";

type DashboardState = {
  agents: Agent[];
  seats: Seat[];
  rollup: FinOpsRollup | null;
};

export function Dashboard() {
  const [data, setData] = useState<DashboardState>({ agents: [], seats: [], rollup: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [agents, seats, rollup] = await Promise.all([
          api.listAgents(),
          api.getSeats().then((res) => res.seats),
          api.projectRollup("tenant-a", "project-a").catch(() => null),
        ]);
        if (active) {
          setData({ agents, seats, rollup });
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load dashboard data");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    load();
    const interval = window.setInterval(load, 10000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const cards = useMemo(
    () => [
      {
        label: "Agents",
        value: data.agents.length.toString(),
        note: data.agents.length ? "registered runtimes" : "no agents registered",
        icon: UsersRound,
      },
      {
        label: "Seats",
        value: data.seats.length.toString(),
        note: `${data.seats.filter((seat) => seat.leased).length} leased`,
        icon: Server,
      },
      {
        label: "Project cost",
        value: data.rollup ? `$${Number(data.rollup.total_cost_usd).toFixed(2)}` : "$0.00",
        note: data.rollup ? `${data.rollup.record_count} cost records` : "tenant-a / project-a",
        icon: CircleDollarSign,
      },
      {
        label: "Runtime burn",
        value: data.agents.filter((agent) => agent.status !== "removed").length.toString(),
        note: "active registry entries",
        icon: Activity,
      },
    ],
    [data],
  );

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Operations Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">Live control-plane data from the local API.</p>
        </div>
        <div className="rounded-md border border-border px-3 py-2 text-xs text-muted-foreground">
          {loading ? "Loading" : error ? "API degraded" : "API connected"}
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="text-xs text-muted-foreground">{card.label}</div>
                <Icon className="size-4 text-muted-foreground" />
              </div>
              <div className="mt-2 text-2xl font-semibold">{loading ? "..." : card.value}</div>
              <div className="mt-1 text-xs text-muted-foreground">{card.note}</div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RuntimeList agents={data.agents} loading={loading} />
        <SeatList seats={data.seats} loading={loading} />
      </div>
    </section>
  );
}

function RuntimeList({ agents, loading }: { agents: Agent[]; loading: boolean }) {
  if (loading) {
    return <Panel title="Agents" rows={["Loading agents"]} />;
  }
  if (!agents.length) {
    return <Panel title="Agents" rows={["No agents registered"]} />;
  }
  return (
    <Panel
      title="Agents"
      rows={agents.map((agent) => `${agent.label} | ${agent.vendor} | ${agent.status}`)}
    />
  );
}

function SeatList({ seats, loading }: { seats: Seat[]; loading: boolean }) {
  if (loading) {
    return <Panel title="Seats" rows={["Loading seats"]} />;
  }
  if (!seats.length) {
    return <Panel title="Seats" rows={["No seats available"]} />;
  }
  return (
    <Panel
      title="Seats"
      rows={seats.map((seat) => `${seat.seat_id} | ${seat.vendor} | refs ${seat.ref_count}`)}
    />
  );
}

function Panel({ title, rows }: { title: string; rows: string[] }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-3 divide-y divide-border">
        {rows.map((row) => (
          <div key={row} className="py-2 text-sm text-muted-foreground">
            {row}
          </div>
        ))}
      </div>
    </div>
  );
}


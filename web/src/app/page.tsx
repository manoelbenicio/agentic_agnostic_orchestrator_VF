"use client";

import { AgentCards } from "@/components/dashboard/AgentCards";
import { SeatCards } from "@/components/dashboard/SeatCards";
import { FinOpsPanel } from "@/components/dashboard/FinOpsPanel";
import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { TaskBoard } from "@/components/dashboard/TaskBoard";
import { ArrowUpRight, Boxes, Cable, Clock3, Radio, Workflow } from "lucide-react";

const lanes = [
  {
    title: "Terminal mode",
    description: "Herdr panes remain available for local-first execution.",
    icon: Cable,
  },
  {
    title: "Socket mode",
    description:
      "Control-plane tasks can claim, dispatch, and report lifecycle state.",
    icon: Workflow,
  },
  {
    title: "Visual builder",
    description: "Drag-and-drop squad topology editor with xyflow canvas.",
    icon: Boxes,
  },
];

export default function Home() {
  return (
    <div className="space-y-6">
      {/* Hero section */}
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-md border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                <Clock3 className="size-3.5" />
                Foundation workspace
              </div>
              <h1 className="text-2xl font-semibold tracking-normal text-foreground md:text-3xl">
                Agnostic Orchestration Platform
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                Enterprise control surface for agent squads, dual execution
                modes, seat-aware runtime isolation, and operational telemetry.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <HealthBadge />
              <a
                href="/live"
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
              >
                <Radio className="size-4" />
                Live Panel
              </a>
              <a
                href="/squad-builder"
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium shadow-sm transition-colors hover:bg-accent"
              >
                Open workspace
                <ArrowUpRight className="size-4" />
              </a>
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="text-sm font-semibold">Execution Modes</div>
          <div className="mt-4 space-y-3">
            {lanes.map((lane) => {
              const Icon = lane.icon;
              return (
                <div
                  key={lane.title}
                  className="flex items-start gap-3 text-sm"
                >
                  <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground">
                    <Icon className="size-4" />
                  </div>
                  <div>
                    <div className="font-medium">{lane.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {lane.description}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Agent cards - live from API */}
      <section>
        <AgentCards />
      </section>

      {/* Seats - live from API */}
      <section>
        <SeatCards />
      </section>

      {/* Task Tracker Board - live from tasks_api */}
      <section>
        <TaskBoard />
      </section>

      {/* FinOps - live from API */}
      <section>
        <FinOpsPanel />
      </section>
    </div>
  );
}

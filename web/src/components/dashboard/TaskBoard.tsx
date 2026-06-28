"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Loader2, CheckSquare } from "lucide-react";
import { api } from "@/lib/api-client";

type TaskStatus = "pending" | "working" | "review" | "held" | "blocked" | "orphaned" | "done";

export type Task = {
  task_id: string;
  title: string;
  priority: string;
  agent: string;
  pane: string;
  status: TaskStatus;
  eta_min: number;
  progress: number;
  herdmaster_task_id: string | null;
  herdmaster_state: string | null;
};

const statusLabels: Record<TaskStatus, string> = {
  pending: "Pending",
  working: "Working",
  review: "Review",
  held: "Held",
  blocked: "Blocked",
  orphaned: "Orphaned",
  done: "Done",
};

export function TaskBoard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadTasks() {
      try {
        const data = await api.listTasks();
        if (!cancelled) setTasks(data);
      } catch (err) {
        if (!cancelled) setError(String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadTasks();
    const timer = setInterval(loadTasks, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (loading && tasks.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-border bg-card">
        <Loader2 className="animate-spin text-accent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Active Tasks Panel */}
      <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckSquare className="size-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold text-foreground">Active Tasks</h2>
          </div>
          <Badge variant="secondary">{tasks.filter(t => t.status !== "done").length} tasks</Badge>
        </div>

        <div className="grid gap-3 lg:grid-cols-3 xl:grid-cols-4">
          {tasks.filter(t => t.status !== "done").map((task) => (
            <div key={task.task_id} className="flex flex-col gap-2 rounded-md border border-border bg-background p-3 shadow-sm transition hover:border-accent">
              <div className="flex items-start justify-between">
                <div className="font-semibold text-sm leading-tight text-foreground">{task.title}</div>
                <Badge variant={task.priority === "P0" ? "destructive" : task.priority === "P1" ? "warning" : "secondary"}>
                  {task.priority}
                </Badge>
              </div>
              
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>Agent: {task.agent}</span>
                <span>Pane: {task.pane}</span>
              </div>

              <div className="mt-2 flex flex-col gap-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-medium">{statusLabels[task.status]}</span>
                  <span>ETA: {task.eta_min}m</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div 
                    className="h-full bg-accent transition-all duration-500" 
                    style={{ width: `${task.progress}%` }} 
                  />
                </div>
                <div className="text-right text-[10px] text-muted-foreground">{task.progress}%</div>
              </div>

              {task.herdmaster_state && (
                <div className="mt-1 flex items-center gap-2 rounded bg-muted/50 p-1.5 text-xs">
                  <span className="font-semibold">HM:</span>
                  <Badge variant="outline">{task.herdmaster_state}</Badge>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Completed Tasks Panel */}
      <div className="rounded-lg border border-border bg-muted/30 p-5 shadow-sm opacity-80">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckSquare className="size-5 text-muted-foreground" />
            <h2 className="text-lg font-semibold text-foreground">Completed Tasks</h2>
          </div>
          <Badge variant="outline">{tasks.filter(t => t.status === "done").length} tasks</Badge>
        </div>

        <div className="grid gap-3 lg:grid-cols-3 xl:grid-cols-4">
          {tasks.filter(t => t.status === "done").map((task) => (
            <div key={task.task_id} className="flex flex-col gap-2 rounded-md border border-border bg-background/50 p-3 shadow-sm grayscale hover:grayscale-0 transition">
              <div className="flex items-start justify-between">
                <div className="font-semibold text-sm leading-tight text-foreground line-through opacity-70">{task.title}</div>
                <Badge variant="outline" className="opacity-70">
                  {task.priority}
                </Badge>
              </div>
              
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground opacity-80">
                <span>Agent: {task.agent}</span>
                <span>Pane: {task.pane}</span>
              </div>

              <div className="mt-2 flex flex-col gap-1.5">
                <div className="flex justify-between text-xs opacity-80">
                  <span className="font-medium text-green-500">{statusLabels[task.status]}</span>
                  <span>ETA: {task.eta_min}m</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div 
                    className="h-full bg-green-500 transition-all duration-500" 
                    style={{ width: `${task.progress}%` }} 
                  />
                </div>
                <div className="text-right text-[10px] text-green-500/80">{task.progress}%</div>
              </div>

              {task.herdmaster_state && (
                <div className="mt-1 flex items-center gap-2 rounded bg-muted/50 p-1.5 text-xs">
                  <span className="font-semibold">HM:</span>
                  <Badge variant="outline">{task.herdmaster_state}</Badge>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

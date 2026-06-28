"use client";

import {
  Archive,
  CheckCircle2,
  FolderKanban,
  Loader2,
  Pencil,
  Play,
  Plus,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

export type ProjectStatus = "active" | "paused" | "archived";
type OperationMode = "terminal" | "socket";

export type Project = {
  project_id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
};

type TaskEvent = {
  status?: string;
  message?: string;
  operation_mode?: OperationMode;
  timestamp?: string;
};

type TaskResult = {
  task_id: string;
  operation_mode: OperationMode;
  events: TaskEvent[];
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

const blankForm = {
  tenant_id: "tenant-a",
  name: "",
  description: "",
  status: "active" as ProjectStatus,
  progress: "0",
};

export function ProjectsClient({
  initialProjects,
  initialError,
}: {
  initialProjects: Project[];
  initialError: string | null;
}) {
  const [projects, setProjects] = useState<Project[]>(initialProjects);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [form, setForm] = useState(blankForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(initialProjects[0]?.project_id ?? "");
  const [taskPrompt, setTaskPrompt] = useState("Run project health check");
  const [taskMode, setTaskMode] = useState<OperationMode>("terminal");
  const [taskRuntime, setTaskRuntime] = useState("runtime-local");
  const [dispatching, setDispatching] = useState(false);
  const [taskResult, setTaskResult] = useState<TaskResult | null>(null);

  useEffect(() => {
    if (!selectedProjectId && projects[0]) {
      setSelectedProjectId(projects[0].project_id);
    }
  }, [projects, selectedProjectId]);

  const grouped = useMemo(
    () => ({
      active: projects.filter((project) => project.status === "active"),
      paused: projects.filter((project) => project.status === "paused"),
      archived: projects.filter((project) => project.status === "archived"),
    }),
    [projects],
  );

  const totalProgress = useMemo(() => {
    if (projects.length === 0) return 0;
    return Math.round(
      projects.reduce((total, project) => total + projectProgress(project), 0) /
        projects.length,
    );
  }, [projects]);

  async function loadProjects() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/projects`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`GET /projects returned ${response.status}`);
      setProjects((await response.json()) as Project[]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }

  async function saveProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const progress = clamp(Number.parseInt(form.progress || "0", 10), 0, 100);
    const body = {
      tenant_id: form.tenant_id.trim(),
      name: form.name.trim(),
      description: form.description.trim() || null,
      status: form.status,
      metadata: { progress_percent: progress },
    };
    const url = editingId ? `${apiBase}/projects/${editingId}` : `${apiBase}/projects`;
    const method = editingId ? "PATCH" : "POST";
    try {
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(editingId ? withoutTenant(body) : body),
      });
      if (!response.ok) throw new Error(`${method} /projects returned ${response.status}`);
      setForm(blankForm);
      setEditingId(null);
      await loadProjects();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  async function deleteProject(projectId: string) {
    setError(null);
    try {
      const response = await fetch(`${apiBase}/projects/${projectId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error(`DELETE /projects returned ${response.status}`);
      if (selectedProjectId === projectId) setSelectedProjectId("");
      await loadProjects();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function dispatchTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setDispatching(true);
    setTaskResult(null);
    setError(null);
    const taskId = `task-${crypto.randomUUID()}`;
    try {
      const response = await fetch(`${apiBase}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          task_id: taskId,
          tenant_id: projectById(projects, selectedProjectId)?.tenant_id ?? "tenant-a",
          project_id: selectedProjectId,
          issue_id: `issue-${selectedProjectId}`,
          assignee_runtime: taskRuntime.trim(),
          prompt: taskPrompt.trim(),
          operation_mode: taskMode,
        }),
      });
      if (!response.ok) throw new Error(`POST /tasks returned ${response.status}`);
      setTaskResult((await response.json()) as TaskResult);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDispatching(false);
    }
  }

  function editProject(project: Project) {
    setEditingId(project.project_id);
    setForm({
      tenant_id: project.tenant_id,
      name: project.name,
      description: project.description ?? "",
      status: project.status,
      progress: String(projectProgress(project)),
    });
  }

  return (
    <main className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
            Projects
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-foreground">
            Project control plane
          </h1>
        </div>
        <Button variant="outline" onClick={() => void loadProjects()} disabled={loading}>
          {loading ? <Loader2 className="animate-spin" /> : <RefreshCcw />}
          Refresh
        </Button>
      </header>

      {error ? (
        <section className="rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <form
          onSubmit={saveProject}
          className="aop-card space-y-4 p-4"
          aria-label={editingId ? "Edit project" : "Create project"}
        >
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-foreground">
              {editingId ? "Edit project" : "Create project"}
            </h2>
            {editingId ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditingId(null);
                  setForm(blankForm);
                }}
              >
                Clear
              </Button>
            ) : null}
          </div>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-foreground">Tenant</span>
            <Input
              value={form.tenant_id}
              disabled={Boolean(editingId)}
              onChange={(event) => setForm({ ...form, tenant_id: event.target.value })}
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-foreground">Name</span>
            <Input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-foreground">Description</span>
            <Input
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">Status</span>
              <Select
                value={form.status}
                onChange={(event) =>
                  setForm({ ...form, status: event.target.value as ProjectStatus })
                }
              >
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="archived">Archived</option>
              </Select>
            </label>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">Progress</span>
              <Input
                min={0}
                max={100}
                type="number"
                value={form.progress}
                onChange={(event) => setForm({ ...form, progress: event.target.value })}
              />
            </label>
          </div>
          <Button type="submit" disabled={saving || !form.name.trim()} className="w-full">
            {saving ? <Loader2 className="animate-spin" /> : editingId ? <CheckCircle2 /> : <Plus />}
            {editingId ? "Save changes" : "Create project"}
          </Button>
        </form>

        <section className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Projects" value={projects.length} />
            <Metric label="Active" value={grouped.active.length} />
            <Metric label="Paused" value={grouped.paused.length} />
            <Metric label="Avg progress" value={`${totalProgress}%`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <ProjectLane
              title="Active"
              projects={grouped.active}
              loading={loading}
              onEdit={editProject}
              onDelete={(projectId) => void deleteProject(projectId)}
            />
            <ProjectLane
              title="Paused"
              projects={grouped.paused}
              loading={loading}
              onEdit={editProject}
              onDelete={(projectId) => void deleteProject(projectId)}
            />
            <ProjectLane
              title="Archived"
              projects={grouped.archived}
              loading={loading}
              onEdit={editProject}
              onDelete={(projectId) => void deleteProject(projectId)}
            />
          </div>
        </section>
      </section>

      <section className="aop-card grid gap-4 p-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <form onSubmit={dispatchTask} className="space-y-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">Dispatch task</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Sends a real POST /tasks request tied to the selected project.
            </p>
          </div>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-foreground">Project</span>
            <Select
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              disabled={projects.length === 0}
            >
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {project.name}
                </option>
              ))}
            </Select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">Mode</span>
              <Select
                value={taskMode}
                onChange={(event) => setTaskMode(event.target.value as OperationMode)}
              >
                <option value="terminal">Terminal</option>
                <option value="socket">Socket</option>
              </Select>
            </label>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">Runtime</span>
              <Input
                value={taskRuntime}
                onChange={(event) => setTaskRuntime(event.target.value)}
                required
              />
            </label>
          </div>
          <label className="block space-y-1 text-sm">
            <span className="font-medium text-foreground">Prompt</span>
            <Input
              value={taskPrompt}
              onChange={(event) => setTaskPrompt(event.target.value)}
              required
            />
          </label>
          <Button
            type="submit"
            disabled={dispatching || projects.length === 0 || !taskPrompt.trim()}
          >
            {dispatching ? <Loader2 className="animate-spin" /> : <Play />}
            Dispatch
          </Button>
        </form>

        <div className="min-h-48 rounded-md border border-border bg-background p-3">
          {taskResult ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-xs text-muted-foreground">
                  {taskResult.task_id}
                </span>
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                  {taskResult.operation_mode}
                </span>
              </div>
              <div className="space-y-2">
                {taskResult.events.map((event, index) => (
                  <div
                    key={`${event.timestamp ?? "event"}-${index}`}
                    className="rounded-md border border-border bg-card p-2 text-sm"
                  >
                    <div className="font-medium text-foreground">
                      {event.status ?? "event"}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {event.message ?? "No event message returned"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex min-h-40 items-center justify-center text-center text-sm text-muted-foreground">
              Dispatch a project task to see the live API response.
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function ProjectLane({
  title,
  projects,
  loading,
  onEdit,
  onDelete,
}: {
  title: string;
  projects: Project[];
  loading: boolean;
  onEdit: (project: Project) => void;
  onDelete: (projectId: string) => void;
}) {
  return (
    <section className="aop-card min-h-72 p-3">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {projects.length}
        </span>
      </div>
      {loading ? (
        <div className="flex h-44 items-center justify-center text-sm text-muted-foreground">
          <Loader2 className="mr-2 animate-spin" /> Loading projects
        </div>
      ) : projects.length === 0 ? (
        <div className="flex h-44 flex-col items-center justify-center rounded-md border border-dashed border-border text-center text-sm text-muted-foreground">
          <FolderKanban className="mb-2 size-7 opacity-60" />
          No projects returned
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => (
            <article key={project.project_id} className="rounded-md border border-border bg-card p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-semibold text-foreground">
                    {project.name}
                  </h3>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                    {project.description ?? "No description recorded"}
                  </p>
                </div>
                <Archive className="size-4 shrink-0 text-muted-foreground" />
              </div>
              <div className="mt-3">
                <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                  <span>Progress</span>
                  <span>{projectProgress(project)}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${projectProgress(project)}%` }}
                  />
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs text-muted-foreground">
                  {project.project_id}
                </span>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Edit ${project.name}`}
                    onClick={() => onEdit(project)}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete ${project.name}`}
                    onClick={() => onDelete(project.project_id)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="aop-card p-3">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-foreground">{value}</div>
    </div>
  );
}

function projectProgress(project: Project) {
  const raw = project.metadata.progress_percent ?? project.metadata.progress;
  return clamp(typeof raw === "number" ? raw : Number.parseInt(String(raw ?? "0"), 10), 0, 100);
}

function clamp(value: number, min: number, max: number) {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function projectById(projects: Project[], projectId: string) {
  return projects.find((project) => project.project_id === projectId);
}

function withoutTenant(body: {
  tenant_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  metadata: Record<string, unknown>;
}) {
  return {
    name: body.name,
    description: body.description,
    status: body.status,
    metadata: body.metadata,
  };
}

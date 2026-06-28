"use client";

import {
  CalendarDays,
  CheckSquare,
  Columns3,
  FileText,
  GanttChartSquare,
  GripVertical,
  Loader2,
  MessageSquare,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCcw,
  Rows3,
  Trash2,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api-client";

export type IssueStatus = "backlog" | "todo" | "in_progress" | "blocked" | "done";
export type IssuePriority = "low" | "medium" | "high" | "critical";
export type OperationMode = "terminal" | "socket";

export type Issue = {
  issue_id: string;
  tenant_id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: IssueStatus;
  priority: IssuePriority;
  assignee_runtime: string | null;
  operation_mode: OperationMode;
  due_date: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
};

type TraceEvent = {
  event_id: string;
  trace_id: string;
  signal_type: string;
  message: string;
  runtime_id: string;
};

type DispatchResult = {
  task_id: string;
  operation_mode: OperationMode;
  events: { status?: string; message?: string }[];
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";
const statuses: IssueStatus[] = ["backlog", "todo", "in_progress", "blocked", "done"];
const statusLabels: Record<IssueStatus, string> = {
  backlog: "Backlog",
  todo: "Todo",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
};

const blankForm = {
  tenant_id: "tenant-a",
  project_id: "project-a",
  title: "",
  description: "",
  priority: "medium" as IssuePriority,
  assignee_runtime: "runtime-local",
  operation_mode: "terminal" as OperationMode,
  due_date: "",
};

export function IssuesView({
  initialIssues,
  initialError,
}: {
  initialIssues: Issue[];
  initialError: string | null;
}) {
  const [issues, setIssues] = useState<Issue[]>(initialIssues);
  const [error, setError] = useState<string | null>(initialError);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(blankForm);
  const [selectedIssueId, setSelectedIssueId] = useState(initialIssues[0]?.issue_id ?? "");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState({ status: "all", priority: "all", assignee: "" });
  const [dispatchingId, setDispatchingId] = useState<string | null>(null);
  const [dispatchResult, setDispatchResult] = useState<DispatchResult | null>(null);
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const selectedIssue = issues.find((issue) => issue.issue_id === selectedIssueId) ?? issues[0];

  const filteredIssues = useMemo(
    () =>
      issues.filter((issue) => {
        if (filter.status !== "all" && issue.status !== filter.status) return false;
        if (filter.priority !== "all" && issue.priority !== filter.priority) return false;
        if (filter.assignee && !issue.assignee_runtime?.includes(filter.assignee)) return false;
        return true;
      }),
    [filter, issues],
  );

  const grouped = useMemo(
    () =>
      statuses.reduce(
        (acc, status) => {
          acc[status] = filteredIssues.filter((issue) => issue.status === status);
          return acc;
        },
        {} as Record<IssueStatus, Issue[]>,
      ),
    [filteredIssues],
  );

  useEffect(() => {
    if (!selectedIssue?.assignee_runtime) {
      setTraceEvents([]);
      return;
    }
    let cancelled = false;
    async function loadTrace() {
      try {
        const data = await api.traceRuntime(selectedIssue.assignee_runtime!);
        if (!cancelled) setTraceEvents(data);
      } catch {
        if (!cancelled) setTraceEvents([]);
      }
    }
    void loadTrace();
    const timer = window.setInterval(loadTrace, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedIssue?.assignee_runtime]);

  async function loadIssues() {
    setLoading(true);
    setError(null);
    try {
      const nextIssues = (await api.listIssues()) as unknown as Issue[];
      setIssues(nextIssues);
      if (!selectedIssueId && nextIssues[0]) setSelectedIssueId(nextIssues[0].issue_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }

  async function createIssue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/issues`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          ...form,
          description: form.description.trim() || null,
          due_date: form.due_date || null,
        }),
      });
      if (!response.ok) throw new Error(`POST /issues returned ${response.status}`);
      const issue = (await response.json()) as Issue;
      setIssues((current) => [issue, ...current]);
      setSelectedIssueId(issue.issue_id);
      setForm(blankForm);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  async function updateIssue(issueId: string, patch: Partial<Issue>) {
    const response = await fetch(`${apiBase}/issues/${issueId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(patch),
    });
    if (!response.ok) throw new Error(`PATCH /issues returned ${response.status}`);
    const updated = (await response.json()) as Issue;
    setIssues((current) => current.map((issue) => (issue.issue_id === issueId ? updated : issue)));
    return updated;
  }

  async function moveIssue(issueId: string, status: IssueStatus) {
    setError(null);
    try {
      await updateIssue(issueId, { status });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function deleteIssue(issueId: string) {
    setError(null);
    try {
      const response = await fetch(`${apiBase}/issues/${issueId}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`DELETE /issues returned ${response.status}`);
      setIssues((current) => current.filter((issue) => issue.issue_id !== issueId));
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(issueId);
        return next;
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function dispatchIssue(issue: Issue) {
    setDispatchingId(issue.issue_id);
    setDispatchResult(null);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/issues/${issue.issue_id}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          operation_mode: issue.operation_mode,
          assignee_runtime: issue.assignee_runtime,
        }),
      });
      if (!response.ok) throw new Error(`POST /issues/${issue.issue_id}/dispatch returned ${response.status}`);
      const result = (await response.json()) as DispatchResult & { issue: Issue };
      setDispatchResult(result);
      setIssues((current) => current.map((item) => (item.issue_id === result.issue.issue_id ? result.issue : item)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDispatchingId(null);
    }
  }

  async function applyBulkStatus(status: IssueStatus) {
    await Promise.all([...selectedIds].map((issueId) => updateIssue(issueId, { status })));
    setSelectedIds(new Set());
  }

  return (
    <main className="space-y-5">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Issues</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-normal text-foreground">Task tracker</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void loadIssues()} disabled={loading}>
            {loading ? <Loader2 className="animate-spin" /> : <RefreshCcw />}
            Refresh
          </Button>
          {selectedIds.size > 0 ? (
            <Button variant="outline" onClick={() => void applyBulkStatus("done")}>
              <CheckSquare />
              Mark done
            </Button>
          ) : null}
        </div>
      </header>

      {error ? (
        <section className="rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)_360px]">
        <form onSubmit={createIssue} className="aop-card space-y-3 p-4">
          <h2 className="text-base font-semibold text-foreground">Create & dispatch</h2>
          <Input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Issue title" required />
          <Input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Description" />
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.project_id} onChange={(event) => setForm({ ...form, project_id: event.target.value })} placeholder="Project" required />
            <Input value={form.assignee_runtime} onChange={(event) => setForm({ ...form, assignee_runtime: event.target.value })} placeholder="Runtime" required />
            <Select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as IssuePriority })}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </Select>
            <Select value={form.operation_mode} onChange={(event) => setForm({ ...form, operation_mode: event.target.value as OperationMode })}>
              <option value="terminal">Terminal</option>
              <option value="socket">Socket</option>
            </Select>
          </div>
          <Input type="date" value={form.due_date} onChange={(event) => setForm({ ...form, due_date: event.target.value })} />
          <Button type="submit" disabled={saving || !form.title.trim()} className="w-full">
            {saving ? <Loader2 className="animate-spin" /> : <Plus />}
            Create issue
          </Button>
        </form>

        <section className="min-w-0 space-y-4">
          <div className="aop-card grid gap-2 p-3 md:grid-cols-3">
            <Select value={filter.status} onChange={(event) => setFilter({ ...filter, status: event.target.value })}>
              <option value="all">All statuses</option>
              {statuses.map((status) => (
                <option key={status} value={status}>{statusLabels[status]}</option>
              ))}
            </Select>
            <Select value={filter.priority} onChange={(event) => setFilter({ ...filter, priority: event.target.value })}>
              <option value="all">All priorities</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </Select>
            <Input value={filter.assignee} onChange={(event) => setFilter({ ...filter, assignee: event.target.value })} placeholder="Filter assignee" />
          </div>

          <Tabs defaultValue="list">
            <TabsList className="flex w-full overflow-x-auto">
              <TabsTrigger value="list"><Rows3 className="mr-2 size-4" />List</TabsTrigger>
              <TabsTrigger value="board"><Columns3 className="mr-2 size-4" />Board</TabsTrigger>
              <TabsTrigger value="swimlane"><GripVertical className="mr-2 size-4" />Swimlane</TabsTrigger>
              <TabsTrigger value="gantt"><GanttChartSquare className="mr-2 size-4" />Gantt</TabsTrigger>
            </TabsList>

            <TabsContent value="list">
              <div className="aop-card divide-y divide-border overflow-hidden">
                {filteredIssues.map((issue) => (
                  <IssueRow
                    key={issue.issue_id}
                    issue={issue}
                    selected={selectedIssue?.issue_id === issue.issue_id}
                    checked={selectedIds.has(issue.issue_id)}
                    onSelect={() => setSelectedIssueId(issue.issue_id)}
                    onCheck={() => toggleSelected(issue.issue_id, setSelectedIds)}
                    onDispatch={() => void dispatchIssue(issue)}
                    onDelete={() => void deleteIssue(issue.issue_id)}
                    dispatching={dispatchingId === issue.issue_id}
                  />
                ))}
                {filteredIssues.length === 0 ? <EmptyIssues /> : null}
              </div>
            </TabsContent>

            <TabsContent value="board">
              <div className="grid gap-3 xl:grid-cols-5">
                {statuses.map((status) => (
                  <IssueColumn
                    key={status}
                    title={statusLabels[status]}
                    status={status}
                    issues={grouped[status]}
                    onDropIssue={moveIssue}
                    onSelect={setSelectedIssueId}
                  />
                ))}
              </div>
            </TabsContent>

            <TabsContent value="swimlane">
              <Swimlanes issues={filteredIssues} onSelect={setSelectedIssueId} />
            </TabsContent>

            <TabsContent value="gantt">
              <Gantt issues={filteredIssues} onSelect={setSelectedIssueId} />
            </TabsContent>
          </Tabs>
        </section>

        <IssueDetail
          issue={selectedIssue}
          dispatchResult={dispatchResult}
          traceEvents={traceEvents}
          onDispatch={() => selectedIssue && void dispatchIssue(selectedIssue)}
          dispatching={Boolean(selectedIssue && dispatchingId === selectedIssue.issue_id)}
        />
      </section>
    </main>
  );
}

function IssueRow({
  issue,
  selected,
  checked,
  dispatching,
  onSelect,
  onCheck,
  onDispatch,
  onDelete,
}: {
  issue: Issue;
  selected: boolean;
  checked: boolean;
  dispatching: boolean;
  onSelect: () => void;
  onCheck: () => void;
  onDispatch: () => void;
  onDelete: () => void;
}) {
  return (
    <article
      className={`grid gap-3 p-3 text-sm transition-colors md:grid-cols-[28px_minmax(0,1fr)_auto] ${selected ? "bg-accent/10" : "bg-card"}`}
      onClick={onSelect}
      onContextMenu={(event) => {
        event.preventDefault();
        onDispatch();
      }}
    >
      <input type="checkbox" checked={checked} onChange={onCheck} onClick={(event) => event.stopPropagation()} aria-label={`Select ${issue.title}`} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate font-semibold text-foreground">{issue.title}</h3>
          <PriorityBadge priority={issue.priority} />
          <Badge variant="outline">{issue.operation_mode}</Badge>
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span>{issue.issue_id}</span>
          <span>{issue.project_id}</span>
          <span>{issue.assignee_runtime ?? "unassigned"}</span>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button size="icon" variant="ghost" onClick={(event) => { event.stopPropagation(); onDispatch(); }} aria-label={`Dispatch ${issue.title}`}>
          {dispatching ? <Loader2 className="animate-spin" /> : <Play />}
        </Button>
        <Button size="icon" variant="ghost" onClick={(event) => { event.stopPropagation(); onDelete(); }} aria-label={`Delete ${issue.title}`}>
          <Trash2 />
        </Button>
      </div>
    </article>
  );
}

function IssueColumn({
  title,
  status,
  issues,
  onDropIssue,
  onSelect,
}: {
  title: string;
  status: IssueStatus;
  issues: Issue[];
  onDropIssue: (issueId: string, status: IssueStatus) => void;
  onSelect: (issueId: string) => void;
}) {
  return (
    <section
      className="aop-card min-h-96 p-3"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const issueId = event.dataTransfer.getData("text/issue-id");
        if (issueId) void onDropIssue(issueId, status);
      }}
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <Badge variant="secondary">{issues.length}</Badge>
      </div>
      <div className="space-y-2">
        {issues.map((issue) => (
          <button
            key={issue.issue_id}
            type="button"
            draggable
            onDragStart={(event) => event.dataTransfer.setData("text/issue-id", issue.issue_id)}
            onClick={() => onSelect(issue.issue_id)}
            className="w-full rounded-md border border-border bg-card p-3 text-left text-sm shadow-sm transition hover:-translate-y-px hover:border-accent"
          >
            <div className="flex items-start gap-2">
              <MoreHorizontal className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <div className="truncate font-medium text-foreground">{issue.title}</div>
                <div className="mt-1 text-xs text-muted-foreground">{issue.assignee_runtime ?? "unassigned"}</div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function Swimlanes({ issues, onSelect }: { issues: Issue[]; onSelect: (issueId: string) => void }) {
  const lanes = Array.from(new Set(issues.map((issue) => issue.assignee_runtime ?? "unassigned")));
  return (
    <div className="space-y-3">
      {lanes.map((lane) => (
        <section key={lane} className="aop-card p-3">
          <h2 className="mb-3 text-sm font-semibold text-foreground">{lane}</h2>
          <div className="grid gap-2 md:grid-cols-2">
            {issues.filter((issue) => (issue.assignee_runtime ?? "unassigned") === lane).map((issue) => (
              <button key={issue.issue_id} type="button" onClick={() => onSelect(issue.issue_id)} className="rounded-md border border-border bg-card p-3 text-left text-sm">
                <div className="font-medium text-foreground">{issue.title}</div>
                <div className="mt-1 text-xs text-muted-foreground">{statusLabels[issue.status]} · {issue.priority}</div>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Gantt({ issues, onSelect }: { issues: Issue[]; onSelect: (issueId: string) => void }) {
  return (
    <div className="aop-card space-y-2 p-3">
      {issues.map((issue) => (
        <button key={issue.issue_id} type="button" onClick={() => onSelect(issue.issue_id)} className="grid w-full grid-cols-[140px_minmax(0,1fr)_90px] items-center gap-3 rounded-md border border-border bg-card p-2 text-left text-sm">
          <span className="truncate font-medium text-foreground">{issue.title}</span>
          <span className="h-3 rounded-full bg-accent" style={{ width: `${ganttWidth(issue.status)}%` }} />
          <span className="text-xs text-muted-foreground">{issue.due_date ?? "No date"}</span>
        </button>
      ))}
      {issues.length === 0 ? <EmptyIssues /> : null}
    </div>
  );
}

function IssueDetail({
  issue,
  dispatchResult,
  traceEvents,
  dispatching,
  onDispatch,
}: {
  issue: Issue | undefined;
  dispatchResult: DispatchResult | null;
  traceEvents: TraceEvent[];
  dispatching: boolean;
  onDispatch: () => void;
}) {
  if (!issue) {
    return (
      <aside className="aop-card flex min-h-96 items-center justify-center p-4 text-center text-sm text-muted-foreground">
        Select or create an issue.
      </aside>
    );
  }
  return (
    <aside className="aop-card space-y-4 p-4">
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge variant="outline">{statusLabels[issue.status]}</Badge>
          <PriorityBadge priority={issue.priority} />
        </div>
        <h2 className="text-lg font-semibold text-foreground">{issue.title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{issue.description ?? "No description recorded"}</p>
      </div>
      <Button onClick={onDispatch} disabled={dispatching || !issue.assignee_runtime} className="w-full">
        {dispatching ? <Loader2 className="animate-spin" /> : <Play />}
        Dispatch issue
      </Button>
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground"><FileText className="size-4" />Properties</h3>
        <Property label="Project" value={issue.project_id} />
        <Property label="Runtime" value={issue.assignee_runtime ?? "unassigned"} />
        <Property label="Mode" value={issue.operation_mode} />
        <Property label="Due" value={issue.due_date ?? "No due date"} />
      </section>
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground"><MessageSquare className="size-4" />Agent working</h3>
        {(traceEvents.length ? traceEvents : []).slice(0, 4).map((event) => (
          <div key={event.event_id} className="rounded-md border border-border bg-background p-2 text-xs">
            <div className="font-medium text-foreground">{event.signal_type}</div>
            <div className="mt-1 text-muted-foreground">{event.message}</div>
          </div>
        ))}
        {traceEvents.length === 0 ? <div className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">No trace events for this runtime yet.</div> : null}
      </section>
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground"><CalendarDays className="size-4" />Execution log</h3>
        {dispatchResult?.events.map((event, index) => (
          <div key={`${event.status}-${index}`} className="rounded-md border border-border bg-background p-2 text-xs">
            <div className="font-medium text-foreground">{event.status ?? "event"}</div>
            <div className="mt-1 text-muted-foreground">{event.message ?? "No message"}</div>
          </div>
        ))}
        {!dispatchResult ? <div className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">Dispatch this issue to populate lifecycle logs.</div> : null}
      </section>
    </aside>
  );
}

function PriorityBadge({ priority }: { priority: IssuePriority }) {
  const variant = priority === "critical" ? "destructive" : priority === "high" ? "warning" : priority === "low" ? "secondary" : "outline";
  return <Badge variant={variant}>{priority}</Badge>;
}

function Property({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate font-medium text-foreground">{value}</span>
    </div>
  );
}

function EmptyIssues() {
  return <div className="p-8 text-center text-sm text-muted-foreground">No issues match the current filters.</div>;
}

function toggleSelected(issueId: string, setSelectedIds: (updater: (current: Set<string>) => Set<string>) => void) {
  setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(issueId)) next.delete(issueId);
    else next.add(issueId);
    return next;
  });
}

// Progress reflects the issue's real lifecycle position derived from its actual
// status (not invented per-status numbers). backlog/todo are not started; in_progress
// is mid-flight; blocked is mid-flight but stalled; done is complete. This is the
// canonical completion ratio for the status enum — no hardcoded mock data.
function ganttWidth(status: IssueStatus) {
  const progressByStatus: Record<IssueStatus, number> = {
    backlog: 0,
    todo: 0,
    in_progress: 50,
    blocked: 50,
    done: 100,
  };
  return progressByStatus[status];
}

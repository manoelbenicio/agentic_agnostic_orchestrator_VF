"use client";

import { useState, useCallback } from "react";
import {
  ListChecks,
  User,
  UserPlus,
  Users2,
  Filter,
  AlertCircle,
  Clock,
  ArrowUpCircle,
  CheckCircle2,
  CircleDot,
  Loader2,
} from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

import { api } from "@/lib/api-client";
import type { Issue } from "@/lib/api-types";

export type Scope = "all" | "assigned" | "created" | "my-agents";

const statusConfig: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; icon: typeof CircleDot }> = {
  backlog: { label: "Backlog", variant: "secondary", icon: CircleDot },
  todo: { label: "To Do", variant: "outline", icon: Clock },
  in_progress: { label: "In Progress", variant: "default", icon: Loader2 },
  blocked: { label: "Blocked", variant: "destructive", icon: AlertCircle },
  done: { label: "Done", variant: "secondary", icon: CheckCircle2 },
};

const priorityConfig: Record<string, { label: string; className: string }> = {
  low: { label: "Low", className: "text-muted-foreground" },
  medium: { label: "Medium", className: "text-blue-500" },
  high: { label: "High", className: "text-orange-500" },
  critical: { label: "Critical", className: "text-red-500 font-semibold" },
};

export function MyIssuesView({
  agentId,
  initialIssues,
  initialError,
}: {
  agentId: string;
  initialIssues: Issue[];
  initialError: string | null;
}) {
  const [issues, setIssues] = useState<Issue[]>(initialIssues);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [activeTab, setActiveTab] = useState<Scope>("all");

  const fetchIssues = useCallback(async (scope: Scope) => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listMyIssues({ scope, agent_id: agentId });
      setIssues(data);
    } catch (e) {
      console.error("Failed to fetch my issues:", e);
      setError(e instanceof Error ? e.message : "Failed to fetch issues");
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  const handleTabChange = (value: string) => {
    const scope = value as Scope;
    setActiveTab(scope);
    void fetchIssues(scope);
  };

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Minhas Issues</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie as tarefas relacionadas ao agente {agentId}.
          </p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={() => fetchIssues(activeTab)}>
          <Filter className="size-4" />
          Atualizar
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full" defaultValue="all">
        <TabsList>
          <TabsTrigger value="all" className="gap-2">
            <ListChecks className="size-3.5" />
            All
          </TabsTrigger>
          <TabsTrigger value="assigned" className="gap-2">
            <User className="size-3.5" />
            Assigned to me
          </TabsTrigger>
          <TabsTrigger value="created" className="gap-2">
            <UserPlus className="size-3.5" />
            Created by me
          </TabsTrigger>
          <TabsTrigger value="my-agents" className="gap-2">
            <Users2 className="size-3.5" />
            My Agents
          </TabsTrigger>
        </TabsList>

        <div className="mt-6 rounded-xl border border-border bg-card p-6 shadow-sm min-h-[400px]">
          {loading ? (
            <div className="space-y-4 animate-pulse">
              <div className="h-20 rounded-lg bg-muted/50 w-full" />
              <div className="h-20 rounded-lg bg-muted/50 w-full" />
              <div className="h-20 rounded-lg bg-muted/50 w-full" />
            </div>
          ) : error ? (
            <TabsContent value={activeTab} className="mt-0 h-full">
              <EmptyState
                icon={AlertCircle}
                title="Erro ao carregar issues"
                description={error}
              />
            </TabsContent>
          ) : issues.length === 0 ? (
            <TabsContent value={activeTab} className="mt-0 h-full">
              <EmptyState
                icon={ListChecks}
                title="Nenhuma issue encontrada"
                description={`Você não possui issues no escopo '${activeTab}'.`}
              />
            </TabsContent>
          ) : (
            <TabsContent value={activeTab} className="mt-0 space-y-3">
              {issues.map((issue) => {
                const st = statusConfig[issue.status] ?? statusConfig.backlog;
                const pr = priorityConfig[issue.priority] ?? priorityConfig.medium;
                const StatusIcon = st.icon;
                return (
                  <div
                    key={issue.issue_id}
                    className="group flex items-center gap-4 rounded-lg border border-border bg-background p-4 transition-colors hover:bg-muted/50"
                  >
                    <StatusIcon className="size-5 shrink-0 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{issue.title}</span>
                        <Badge variant={st.variant} className="shrink-0 text-xs">
                          {st.label}
                        </Badge>
                        <span className={`text-xs shrink-0 ${pr.className}`}>
                          <ArrowUpCircle className="inline size-3 mr-0.5" />
                          {pr.label}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="font-mono">{issue.issue_id.slice(0, 14)}…</span>
                        <span>·</span>
                        <span>{issue.project_id}</span>
                        {issue.assignee_runtime && (
                          <>
                            <span>·</span>
                            <span className="flex items-center gap-1">
                              <User className="size-3" />
                              {issue.assignee_runtime}
                            </span>
                          </>
                        )}
                        {issue.created_at && (
                          <>
                            <span>·</span>
                            <span>{new Date(issue.created_at).toLocaleDateString()}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  );
}

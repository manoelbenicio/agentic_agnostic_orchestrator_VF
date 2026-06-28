import { MyIssuesView, type Scope } from "@/components/my-issues/my-issues-view";
import { api } from "@/lib/api-client";
import type { Issue } from "@/lib/api-types";

export const metadata = {
  title: "Minhas Issues — AOP",
  description: "Visualize e gerencie issues atribuídas a você e seus agentes.",
};

const agentId = process.env.NEXT_PUBLIC_AGENT_ID ?? "w8:pS";

async function loadMyIssues(scope: Scope): Promise<{ issues: Issue[]; error: string | null }> {
  try {
    const issues = await api.listMyIssues({ scope, agent_id: agentId });
    return { issues, error: null };
  } catch (cause) {
    return {
      issues: [],
      error: cause instanceof Error ? cause.message : String(cause),
    };
  }
}

export default async function MyIssuesPage() {
  const { issues, error } = await loadMyIssues("all");
  return <MyIssuesView agentId={agentId} initialIssues={issues} initialError={error} />;
}

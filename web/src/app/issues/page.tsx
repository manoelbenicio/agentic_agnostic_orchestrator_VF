import { IssuesView, type Issue } from "@/components/issues/issues-view";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

async function loadIssues(): Promise<{ issues: Issue[]; error: string | null }> {
  try {
    const response = await fetch(`${apiBase}/issues`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return { issues: [], error: `GET /issues returned ${response.status}` };
    }
    return { issues: (await response.json()) as Issue[], error: null };
  } catch (cause) {
    return {
      issues: [],
      error: cause instanceof Error ? cause.message : String(cause),
    };
  }
}

export default async function IssuesPage() {
  const { issues, error } = await loadIssues();
  return <IssuesView initialIssues={issues} initialError={error} />;
}

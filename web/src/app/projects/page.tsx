import { ProjectsClient, type Project } from "./projects-client";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

async function loadProjects(): Promise<{
  projects: Project[];
  error: string | null;
}> {
  try {
    const response = await fetch(`${apiBase}/projects`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return { projects: [], error: `GET /projects returned ${response.status}` };
    }
    return { projects: (await response.json()) as Project[], error: null };
  } catch (cause) {
    return {
      projects: [],
      error: cause instanceof Error ? cause.message : String(cause),
    };
  }
}

export default async function ProjectsPage() {
  const { projects, error } = await loadProjects();

  return <ProjectsClient initialProjects={projects} initialError={error} />;
}

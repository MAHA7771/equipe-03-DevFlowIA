import type { Project } from "@/types/contracts";
import { api, USE_MOCK, delay } from "./api";
import { mockProjects } from "./mock";

export async function listProjects(): Promise<Project[]> {
  if (USE_MOCK) {
    await delay();
    return mockProjects;
  }
  return api<Project[]>("/api/projects");
}

export async function linkRepository(projectId: string, owner: string, name: string): Promise<Project> {
  if (USE_MOCK) {
    await delay();
    const p = mockProjects.find((x) => x.project_id === projectId);
    if (!p) throw new Error("Projet introuvable");
    p.repository = {
      provider: "github",
      owner,
      name,
      default_branch: "main",
      installation_id: 12345678,
      linked_at: new Date().toISOString(),
    };
    return p;
  }
  return api<Project>(`/api/projects/${projectId}/repository`, {
    method: "POST",
    body: JSON.stringify({ owner, name }),
  });
}
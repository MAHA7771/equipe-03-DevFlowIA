import type { Repository } from "@/types/contracts";
import { api, USE_MOCK, delay } from "./api";
import { mockRepositories } from "./mock";

export async function listRepositories(): Promise<Repository[]> {
  if (USE_MOCK) {
    await delay();
    return mockRepositories;
  }
  return api<Repository[]>("/api/github/repositories");
}
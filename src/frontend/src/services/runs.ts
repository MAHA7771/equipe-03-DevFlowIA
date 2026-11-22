import type { Run, StoryProposal, StoriesValidated, TraceEvent } from "@/types/contracts";
import { api, USE_MOCK, delay } from "./api";
import { mockRun, mockProposal, mockEvents } from "./mock";

export async function getRun(runId: string): Promise<Run> {
  if (USE_MOCK) {
    await delay(150);
    return { ...mockRun, run_id: runId };
  }
  return api<Run>(`/api/runs/${runId}`);
}

export async function getStories(runId: string): Promise<StoryProposal> {
  if (USE_MOCK) {
    await delay();
    return { ...mockProposal, run_id: runId };
  }
  return api<StoryProposal>(`/api/runs/${runId}/stories`);
}

export async function getEvents(runId: string): Promise<TraceEvent[]> {
  if (USE_MOCK) {
    await delay(150);
    return mockEvents.map((e) => ({ ...e, run_id: runId }));
  }
  return api<TraceEvent[]>(`/api/runs/${runId}/events`);
}

export async function validateStories(runId: string, payload: StoriesValidated): Promise<void> {
  if (USE_MOCK) {
    await delay();
    mockRun.state = payload.decision === "approved" ? "STORIES_VALIDATED" : "STORIES_PROPOSED";
    mockRun.updated_at = new Date().toISOString();
    return;
  }
  await api<unknown>(`/api/runs/${runId}/stories/validate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
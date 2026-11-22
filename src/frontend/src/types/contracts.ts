// Types TypeScript alignés sur les contrats C0 à C12 (docs/contrats-donnees.md)

export type RunState =
  | "RECEIVED"
  | "TRIAGED"
  | "NEEDS_CLARIFICATION"
  | "STORIES_PROPOSED"
  | "AWAITING_VALIDATION"
  | "STORIES_VALIDATED"
  | "JIRA_SYNCED"
  | "REPO_ANALYZED"
  | "DEVELOPING"
  | "QA_RUNNING"
  | "PR_READY"
  | "AWAITING_HUMAN_REVIEW"
  | "DONE"
  | "FAILED";

// C0
export interface Repository {
  provider: string;
  owner: string;
  name: string;
  default_branch: string;
  installation_id: number | null;
  linked_at: string | null;
}

export interface Project {
  project_id: string;
  name: string;
  repository: Repository | null;
}

export interface Run {
  run_id: string;
  project_id: string;
  state: RunState;
  email_subject: string | null;
  updated_at: string;
}

// C3
export interface Story {
  story_id: string;
  title: string;
  description: string;
  acceptance_criteria: string[];
  depends_on: string[];
  requirement_ids: string[];
  status: string;
}

export interface StoryProposal {
  run_id: string;
  project_id: string;
  epic: { title: string; description: string };
  stories: Story[];
}

// C4
export interface StoriesValidated {
  run_id: string;
  decision: "approved" | "changes_requested";
  validated_by: string;
  validated_at: string;
  stories: Story[];
}

// C12
export interface TraceEvent {
  run_id: string;
  step: string;
  agent: string;
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
  timestamp: string;
}
import type { Project, Run, StoryProposal, TraceEvent, Repository } from "@/types/contracts";

export const mockRepositories: Repository[] = [
  { provider: "github", owner: "acme", name: "shop-api", default_branch: "main", installation_id: 12345678, linked_at: null },
  { provider: "github", owner: "acme", name: "blog-api", default_branch: "main", installation_id: 12345678, linked_at: null },
  { provider: "github", owner: "acme", name: "demo-devflow", default_branch: "main", installation_id: 12345678, linked_at: null },
];

export const mockProjects: Project[] = [
  {
    project_id: "prj_001",
    name: "Boutique e-commerce",
    repository: { ...mockRepositories[0], linked_at: "2026-11-22T10:00:00Z" },
  },
  { project_id: "prj_002", name: "Blog interne", repository: null },
];

export const mockRun: Run = {
  run_id: "run_001",
  project_id: "prj_001",
  state: "AWAITING_VALIDATION",
  email_subject: "Nouvelles fonctionnalités boutique",
  updated_at: "2026-11-22T10:45:00Z",
};

export const mockProposal: StoryProposal = {
  run_id: "run_001",
  project_id: "prj_001",
  epic: { title: "Boutique en ligne", description: "Permettre l'achat en ligne de bout en bout." },
  stories: [
    {
      story_id: "US-01",
      title: "Inscription et connexion",
      description: "En tant que client, je veux créer un compte et me connecter.",
      acceptance_criteria: ["Un client peut créer un compte", "Un client peut se connecter avec son e-mail"],
      depends_on: [],
      requirement_ids: ["REQ-01"],
      status: "proposed",
    },
    {
      story_id: "US-03",
      title: "Gestion du panier",
      description: "En tant que client, je veux gérer mon panier.",
      acceptance_criteria: [
        "Un client peut ajouter un produit au panier",
        "Le total du panier est recalculé automatiquement",
      ],
      depends_on: ["US-01"],
      requirement_ids: ["REQ-02"],
      status: "proposed",
    },
  ],
};

export const mockEvents: TraceEvent[] = [
  { run_id: "run_001", step: "ingest", agent: "email", code: "EMAIL_RECEIVED", message: "E-mail reçu et normalisé", retryable: false, details: {}, timestamp: "2026-11-22T09:30:00Z" },
  { run_id: "run_001", step: "triage", agent: "triage", code: "TRIAGE_DONE", message: "Triage terminé, 3 exigences détectées", retryable: false, details: {}, timestamp: "2026-11-22T09:31:00Z" },
  { run_id: "run_001", step: "decomposition", agent: "decomposition", code: "STORIES_PROPOSED", message: "2 Stories proposées", retryable: false, details: {}, timestamp: "2026-11-22T09:33:00Z" },
];
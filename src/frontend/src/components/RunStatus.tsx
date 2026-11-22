import type { RunState } from "@/types/contracts";

const STEPS: { state: RunState; label: string }[] = [
  { state: "RECEIVED", label: "Reçu" },
  { state: "TRIAGED", label: "Triage" },
  { state: "STORIES_PROPOSED", label: "Stories proposées" },
  { state: "AWAITING_VALIDATION", label: "Validation PO" },
  { state: "STORIES_VALIDATED", label: "Validé" },
  { state: "JIRA_SYNCED", label: "Jira" },
  { state: "REPO_ANALYZED", label: "Analyse repo" },
  { state: "DEVELOPING", label: "Développement" },
  { state: "QA_RUNNING", label: "QA" },
  { state: "PR_READY", label: "PR créée" },
  { state: "AWAITING_HUMAN_REVIEW", label: "Revue humaine" },
  { state: "DONE", label: "Terminé" },
];

export default function RunStatus({ state }: { state: RunState }) {
  const idx = STEPS.findIndex((s) => s.state === state);
  const isFailed = state === "FAILED";
  const isClarif = state === "NEEDS_CLARIFICATION";
  const percent = idx < 0 ? 0 : Math.round((idx / (STEPS.length - 1)) * 100);
  const badge = isFailed ? "badge-red" : isClarif ? "badge-orange" : state === "DONE" ? "badge-green" : "badge-blue";

  return (
    <div>
      <div className="row-between">
        <span className={`badge ${badge}`}>{state}</span>
        <span className="muted">{percent}% du parcours</span>
      </div>
      <div className="progress">
        <div className="progress-bar" style={{ width: `${percent}%` }} />
      </div>
      {isClarif && <p className="error">Une précision est nécessaire : retour au Product Owner.</p>}
      {isFailed && <p className="error">Le run a échoué (voir les événements).</p>}
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s.state} className={i < idx ? "done" : i === idx ? "current" : ""}>
            {i < idx ? "✓ " : ""}
            {s.label}
          </li>
        ))}
      </ol>
    </div>
  );
}
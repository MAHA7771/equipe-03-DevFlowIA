"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRun } from "@/hooks/useRun";
import RunStatus from "@/components/RunStatus";
import EventList from "@/components/EventList";

export default function RunPage() {
  const { runId } = useParams<{ runId: string }>();
  const { run, events, loading, error } = useRun(runId);

  if (loading) return <p className="muted">Chargement…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!run) return <p>Run introuvable.</p>;

  return (
    <div>
      <div className="page-head">
        <h1>Run {run.run_id}</h1>
        <p className="muted">
          Projet {run.project_id} · « {run.email_subject} » · mis à jour le{" "}
          {new Date(run.updated_at).toLocaleString("fr-FR")}
        </p>
      </div>

      <div className="card">
        <h3>Avancement</h3>
        <RunStatus state={run.state} />
        {run.state === "AWAITING_VALIDATION" && (
          <div style={{ marginTop: 16 }}>
            <p className="muted">Les Stories proposées attendent votre validation.</p>
            <Link className="btn" href={`/runs/${run.run_id}/review`}>Relire et valider les Stories</Link>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Événements</h3>
        <EventList events={events} />
      </div>
    </div>
  );
}
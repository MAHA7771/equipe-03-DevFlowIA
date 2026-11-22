"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import type { Story, StoryProposal } from "@/types/contracts";
import { getStories, validateStories } from "@/services/runs";
import StoryCard from "@/components/StoryCard";

export default function ReviewPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const [proposal, setProposal] = useState<StoryProposal | null>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [email, setEmail] = useState("po@client.com");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getStories(runId)
      .then((p) => {
        setProposal(p);
        setStories(p.stories);
      })
      .catch((e) => setError((e as Error).message));
  }, [runId]);

  function updateStory(updated: Story) {
    setStories((prev) => prev.map((s) => (s.story_id === updated.story_id ? updated : s)));
  }

  async function submit(decision: "approved" | "changes_requested") {
    setSaving(true);
    try {
      await validateStories(runId, {
        run_id: runId,
        decision,
        validated_by: email,
        validated_at: new Date().toISOString(),
        stories,
      });
      router.push(`/runs/${runId}`);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!proposal) return <p className="muted">Chargement…</p>;

  return (
    <div>
      <p><Link href={`/runs/${runId}`}>← Retour au run</Link></p>
      <div className="page-head">
        <h1>Revue humaine</h1>
        <p className="muted">Relisez les Stories proposées, corrigez-les si besoin, puis validez.</p>
      </div>

      <div className="card" style={{ borderLeft: "4px solid var(--primary)" }}>
        <span className="badge badge-blue">Epic</span>
        <h3 style={{ marginTop: 8 }}>{proposal.epic.title}</h3>
        <p className="muted" style={{ margin: 0 }}>{proposal.epic.description}</p>
      </div>

      <h2>{stories.length} Stories proposées</h2>
      {stories.map((s) => (
        <StoryCard key={s.story_id} story={s} onChange={updateStory} />
      ))}

      <div className="card">
        <label style={{ marginTop: 0 }}>Validé par</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} />
        <div className="actions" style={{ marginTop: 6 }}>
          <button className="btn" disabled={saving} onClick={() => submit("approved")}>
            ✓ Valider les Stories
          </button>
          <button className="btn btn-secondary" disabled={saving} onClick={() => submit("changes_requested")}>
            Renvoyer à la décomposition
          </button>
        </div>
        <p className="muted" style={{ marginTop: 12, marginBottom: 0 }}>
          Aucune tâche Jira n'est créée avant cette validation.
        </p>
      </div>
    </div>
  );
}
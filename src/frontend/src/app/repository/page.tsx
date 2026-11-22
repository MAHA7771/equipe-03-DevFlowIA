"use client";
import { useState } from "react";
import type { Repository } from "@/types/contracts";
import { useProjects } from "@/hooks/useProjects";
import { linkRepository } from "@/services/projects";
import RepoSelector from "@/components/RepoSelector";

export default function RepositoryPage() {
  const { projects, reload } = useProjects();
  const [projectId, setProjectId] = useState("");
  const [repo, setRepo] = useState<Repository | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!projectId || !repo) return;
    try {
      await linkRepository(projectId, repo.owner, repo.name);
      setMsg(`Le repository ${repo.owner}/${repo.name} est associé au projet ${projectId}.`);
      setError(null);
      reload();
    } catch (e) {
      setError((e as Error).message);
      setMsg(null);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Associer un repository</h1>
        <p className="muted">Chaque e-mail reçu pour ce projet utilisera ce repository : le système ne devine jamais.</p>
      </div>

      <div className="card">
        <h3>1. Choisir le projet</h3>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">Sélectionner un projet…</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>{p.name}</option>
          ))}
        </select>
      </div>

      <div className="card">
        <h3>2. Choisir le repository GitHub</h3>
        <RepoSelector onSelect={setRepo} />
      </div>

      <button className="btn" disabled={!projectId || !repo} onClick={save}>Associer le repository</button>
      {msg && <p className="success" style={{ marginTop: 14 }}>{msg}</p>}
      {error && <p className="error" style={{ marginTop: 14 }}>{error}</p>}
    </div>
  );
}
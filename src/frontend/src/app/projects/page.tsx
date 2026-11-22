"use client";
import Link from "next/link";
import { useProjects } from "@/hooks/useProjects";

export default function ProjectsPage() {
  const { projects, loading, error } = useProjects();

  return (
    <div>
      <div className="page-head">
        <h1>Projets</h1>
        <p className="muted">Chaque projet est relié à un seul repository GitHub.</p>
      </div>

      {loading && <p className="muted">Chargement…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && projects.length === 0 && <div className="card empty">Aucun projet pour l'instant.</div>}

      <div className="grid">
        {projects.map((p) => (
          <div key={p.project_id} className="card">
            <div className="row">
              <div className="avatar">{p.name.charAt(0).toUpperCase()}</div>
              <div>
                <h3 style={{ margin: 0 }}>{p.name}</h3>
                <span className="muted">{p.project_id}</span>
              </div>
            </div>
            <div style={{ marginTop: 14 }}>
              {p.repository ? (
                <>
                  <span className="badge badge-green">Repository associé</span>
                  <p style={{ marginTop: 8 }}>
                    <b>{p.repository.owner}/{p.repository.name}</b>{" "}
                    <span className="muted">· branche {p.repository.default_branch}</span>
                  </p>
                </>
              ) : (
                <>
                  <span className="badge badge-orange">Aucun repository</span>
                  <p style={{ marginTop: 8 }}><Link href="/repository">Associer un repository →</Link></p>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
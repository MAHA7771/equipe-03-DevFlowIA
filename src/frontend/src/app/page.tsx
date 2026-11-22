"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

const STEPS = [
  { t: "E-mail du PO", d: "Le Product Owner envoie sa demande à l'adresse du projet." },
  { t: "Stories par l'IA", d: "DevFlow trie la demande et propose des User Stories." },
  { t: "Validation humaine", d: "Vous relisez, modifiez et validez les Stories." },
  { t: "Code et Pull Request", d: "L'IA développe sur une branche, teste et ouvre une PR." },
];

export default function Home() {
  const [runId, setRunId] = useState("run_001");
  const router = useRouter();

  return (
    <div>
      <section className="hero">
        <h1>De l'e-mail à la Pull Request</h1>
        <p>
          DevFlow AI transforme la demande d'un Product Owner en Stories, en code et en Pull Request,
          avec une validation humaine à chaque étape clé.
        </p>
        <Link href="/runs/run_001" className="btn">Voir un run en cours</Link>
      </section>

      <h2>Comment ça marche</h2>
      <div className="how">
        {STEPS.map((s, i) => (
          <div key={s.t} className="how-step">
            <div className="how-num">{i + 1}</div>
            <h3>{s.t}</h3>
            <p className="muted">{s.d}</p>
          </div>
        ))}
      </div>

      <div className="grid">
        <Link href="/projects" className="card link-card">
          <div className="icon">📁</div>
          <h3>Projets</h3>
          <p className="muted">Voir les projets et leur repository associé.</p>
        </Link>
        <Link href="/repository" className="card link-card">
          <div className="icon">🔗</div>
          <h3>Associer un repository</h3>
          <p className="muted">Relier un projet à un repository GitHub.</p>
        </Link>
      </div>

      <div className="card">
        <h3>Ouvrir un run</h3>
        <div className="row">
          <input style={{ maxWidth: 260 }} value={runId} onChange={(e) => setRunId(e.target.value)} placeholder="run_001" />
          <button className="btn" style={{ marginTop: 0 }} onClick={() => router.push(`/runs/${runId}`)}>
            Ouvrir
          </button>
        </div>
      </div>
    </div>
  );
}
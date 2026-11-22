"use client";
import { useEffect, useState } from "react";
import type { Repository } from "@/types/contracts";
import { listRepositories } from "@/services/github";

interface Props {
  onSelect: (repo: Repository) => void;
}

export default function RepoSelector({ onSelect }: Props) {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    listRepositories()
      .then(setRepos)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="muted">Chargement des repositories…</p>;
  if (error) return <p className="error">{error}</p>;

  return (
    <div>
      {repos.map((r) => {
        const key = `${r.owner}/${r.name}`;
        return (
          <label key={key} className="radio">
            <input
              type="radio"
              name="repo"
              checked={selected === key}
              onChange={() => {
                setSelected(key);
                onSelect(r);
              }}
            />
            {key} <span className="muted">({r.default_branch})</span>
          </label>
        );
      })}
    </div>
  );
}
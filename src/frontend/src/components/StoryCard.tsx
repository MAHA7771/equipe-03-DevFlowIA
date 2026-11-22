"use client";
import type { Story } from "@/types/contracts";

interface Props {
  story: Story;
  onChange: (s: Story) => void;
}

export default function StoryCard({ story, onChange }: Props) {
  return (
    <div className="card">
      <div className="row-between">
        <span className="badge badge-blue">{story.story_id}</span>
        {story.depends_on.length > 0 ? (
          <span className="badge badge-gray">dépend de {story.depends_on.join(", ")}</span>
        ) : (
          <span className="badge badge-green">indépendante</span>
        )}
      </div>

      <label>Titre</label>
      <input value={story.title} onChange={(e) => onChange({ ...story, title: e.target.value })} />

      <label>Description</label>
      <textarea
        rows={2}
        value={story.description}
        onChange={(e) => onChange({ ...story, description: e.target.value })}
      />

      <label>Critères d'acceptation (un par ligne)</label>
      <textarea
        rows={4}
        value={story.acceptance_criteria.join("\n")}
        onChange={(e) =>
          onChange({
            ...story,
            acceptance_criteria: e.target.value.split("\n").filter((l) => l.trim() !== ""),
          })
        }
      />
      <p className="muted" style={{ marginTop: 6 }}>
        {story.acceptance_criteria.length} critère(s) · exigences : {story.requirement_ids.join(", ") || "aucune"}
      </p>
    </div>
  );
}
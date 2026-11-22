import type { TraceEvent } from "@/types/contracts";

export default function EventList({ events }: { events: TraceEvent[] }) {
  if (events.length === 0) return <p className="muted">Aucun événement pour l'instant.</p>;
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Heure</th>
          <th>Étape</th>
          <th>Agent</th>
          <th>Code</th>
          <th>Message</th>
        </tr>
      </thead>
      <tbody>
        {events.map((e, i) => (
          <tr key={i}>
            <td>{new Date(e.timestamp).toLocaleString("fr-FR")}</td>
            <td>{e.step}</td>
            <td>{e.agent}</td>
            <td>
              <span className={`badge ${e.retryable ? "badge-orange" : "badge-gray"}`}>{e.code}</span>
            </td>
            <td>{e.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
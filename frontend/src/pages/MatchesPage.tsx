import { Link } from "react-router-dom";
import type { MatchRead } from "../api/types";

export function MatchesPage({ matches }: { matches: MatchRead[] }) {
  return <section className="panel">
    <div className="panel-header"><h1>Match archive</h1><span>{matches.length} matches</span></div>
    <div className="archive-list">
      {matches.map((match) => <Link className="archive-row" key={match.id} to={`/matches/${match.id}`}>
        <strong>Match #{match.id}</strong>
        <span>{match.map_name ?? "Map pending"}</span>
        <span>{match.score_red ?? "-"} : {match.score_blu ?? "-"}</span>
        <span className="pill">{match.status}</span>
      </Link>)}
      {!matches.length && <p className="muted">No matches have been recorded yet.</p>}
    </div>
  </section>;
}

import { Link } from "react-router-dom";
import type { MatchRead } from "../api/types";

interface MatchCardProps {
  match: MatchRead | null;
}

export function MatchCard({ match }: MatchCardProps) {
  if (!match) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>Current Match</h2>
        </div>
        <p className="muted">No active match right now.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Current Match</h2>
        <span className="pill pill-info">{match.status}</span>
      </div>
      <p>
        {match.map_name ?? "Map TBD"} | RED {match.score_red ?? 0} - {match.score_blu ?? 0} BLU
      </p>
      <div className="team-grid">
        {["RED", "BLU"].map((team) => (
          <div className="team-panel" key={team}>
            <h3>{team}</h3>
            {match.slots
              .filter((slot) => slot.team === team)
              .map((slot) => (
                <div className="team-row" key={`${team}-${slot.player_id}`}>
                  <span>{slot.display_name ?? slot.discord_username}</span>
                  <span>{slot.assigned_class}</span>
                </div>
              ))}
          </div>
        ))}
      </div>
      <p className="muted">
        Logs:{" "}
        {match.log_ids.length > 0 ? match.log_ids.map((id) => <Link key={id} to={`/matches/${match.id}`}>#{id}</Link>) : "Awaiting logs.tf link"}
      </p>
    </section>
  );
}


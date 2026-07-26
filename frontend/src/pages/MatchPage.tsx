import type { MatchRead } from "../api/types";

interface MatchPageProps {
  match: MatchRead | null;
}

export function MatchPage({ match }: MatchPageProps) {
  if (!match) {
    return (
      <section className="panel">
        <h1>Match not found</h1>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h1>Match #{match.id}</h1>
        <span className="pill pill-info">{match.status}</span>
      </div>
      <p>
        {match.map_name ?? "Map TBD"} | RED {match.score_red ?? 0} - {match.score_blu ?? 0} BLU
      </p>
      {match.voice_channel_url && <a className="button-link" href={match.voice_channel_url} target="_blank" rel="noreferrer">
        Join match voice channel
      </a>}
      <div className="team-grid">
        {["RED", "BLU"].map((team) => (
          <div className="team-panel" key={team}>
            <h2>{team}</h2>
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
      <div className="match-meta">
        <strong>Logs</strong>
        {match.log_ids.length > 0 ? match.log_ids.map((logId) => (
          <a key={logId} href={`https://logs.tf/${logId}`} target="_blank" rel="noreferrer">logs.tf/{logId}</a>
        )) : <span className="muted">None yet</span>}
      </div>
      {match.substitutions.length > 0 && <div className="substitution-list">
        <h2>Substitutions</h2>
        {match.substitutions.map((item) => <p key={`${item.outgoing_player_id}-${item.created_at}`}>
          {item.incoming_name} replaced {item.outgoing_name} on {item.team} {item.assigned_class}
        </p>)}
      </div>}
    </section>
  );
}

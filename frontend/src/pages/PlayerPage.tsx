import type { PlayerRead } from "../api/types";

interface PlayerPageProps {
  player: PlayerRead | null;
}

export function PlayerPage({ player }: PlayerPageProps) {
  if (!player) {
    return (
      <section className="panel">
        <h1>Player not found</h1>
      </section>
    );
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>{player.display_name ?? player.discord_username}</h1>
          <span className={`pill ${player.steam_connected ? "pill-good" : "pill-warn"}`}>
            {player.steam_connected ? "Steam linked" : "Steam missing"}
          </span>
        </div>
        <p>Discord: {player.discord_username}</p>
        <p>Steam: {player.steam_name ?? "Not connected"}</p>
        <p>Last sync: {player.last_synced_at ?? "Never"}</p>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>Aggregate Stats</h2>
        </div>
        {player.aggregate ? (
          <div className="stat-grid">
            <div>
              <strong>{player.aggregate.matches_played}</strong>
              <span>Matches</span>
            </div>
            <div>
              <strong>{player.aggregate.wins}</strong>
              <span>Wins</span>
            </div>
            <div>
              <strong>{player.aggregate.kills}</strong>
              <span>Kills</span>
            </div>
            <div>
              <strong>{player.aggregate.damage}</strong>
              <span>Damage</span>
            </div>
            <div>
              <strong>{player.aggregate.healing}</strong>
              <span>Healing</span>
            </div>
          </div>
        ) : (
          <p className="muted">No ingested match data yet.</p>
        )}
      </section>
    </div>
  );
}


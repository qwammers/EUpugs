import type { PlayerRead } from "../api/types";

interface PlayerPageProps {
  player: PlayerRead | null;
}

const decimal = (value: number) => value.toFixed(1);

export function PlayerPage({ player }: PlayerPageProps) {
  if (!player) return <section className="panel"><h1>Player not found</h1></section>;

  const aggregate = player.aggregate;
  const decided = aggregate ? aggregate.wins + aggregate.losses : 0;
  const winRate = aggregate && decided ? aggregate.wins / decided * 100 : 0;
  const kd = aggregate ? (aggregate.deaths ? aggregate.kills / aggregate.deaths : aggregate.kills) : 0;
  const dpm = aggregate?.combat_time_seconds
    ? aggregate.combat_damage / aggregate.combat_time_seconds * 60
    : 0;

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>{player.display_name ?? player.discord_username}</h1>
          <span className={`pill ${player.steam_connected ? "pill-good" : "pill-warn"}`}>
            {player.steam_connected ? "Steam linked" : "Imported profile"}
          </span>
        </div>
        <p>Discord: {player.discord_user_id.startsWith("logstf:") ? "Not linked" : player.discord_username}</p>
        <p>Steam: {player.steam_name ?? "Not connected"}</p>
        <p>Last sync: {player.last_synced_at ?? "Historical import"}</p>
      </section>
      <section className="panel">
        <div className="panel-header"><h2>Overall Stats</h2></div>
        {aggregate ? <div className="stat-grid profile-stat-grid">
          <div><strong>{aggregate.matches_played}</strong><span>Matches</span></div>
          <div><strong>{aggregate.wins}</strong><span>Wins</span></div>
          <div><strong>{aggregate.losses}</strong><span>Losses</span></div>
          <div><strong className={winRate >= 50 ? "win-rate-good" : "win-rate-bad"}>{decimal(winRate)}%</strong><span>Win rate</span></div>
          <div><strong>{decimal(kd)}</strong><span>K/D</span></div>
          <div><strong>{Math.round(dpm)}</strong><span>Non-Medic DPM</span></div>
        </div> : <p className="muted">No ingested match data yet.</p>}
      </section>
      <section className="panel spotlight">
        <div className="panel-header"><h2>Class Breakdown</h2></div>
        {player.class_stats.length ? <div className="leaderboard-scroll">
          <table className="leaderboard-table class-stats-table">
            <thead><tr><th>Class</th><th>MP</th><th>W</th><th>L</th><th>Win%</th><th>K</th><th>D</th><th>A</th><th>K/D</th><th>DPM</th></tr></thead>
            <tbody>{player.class_stats.map((row) => <tr key={row.class_name}>
              <td className="class-name">{row.class_name}</td>
              <td>{row.matches_played}</td><td>{row.wins}</td><td>{row.losses}</td>
              <td className={row.win_percentage >= 50 ? "win-rate-good" : "win-rate-bad"}>{decimal(row.win_percentage)}%</td>
              <td>{row.kills}</td><td>{row.deaths}</td><td>{row.assists}</td>
              <td>{decimal(row.kill_death_ratio)}</td><td>{Math.round(row.damage_per_minute)}</td>
            </tr>)}</tbody>
          </table>
        </div> : <p className="muted">No class-level data is available yet.</p>}
      </section>
    </div>
  );
}

import { Link } from "react-router-dom";
import type { LeaderboardEntry } from "../api/types";

interface LeaderboardPageProps {
  entries: LeaderboardEntry[];
}

export function LeaderboardPage({ entries }: LeaderboardPageProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h1>Leaderboard</h1>
        <span>{entries.length} tracked players</span>
      </div>
      <div className="table">
        <div className="table-head">
          <span>Player</span>
          <span>W</span>
          <span>K</span>
          <span>D</span>
          <span>A</span>
          <span>DMG</span>
        </div>
        {entries.map((entry) => (
          <Link className="table-row" key={entry.player_id} to={`/players/${entry.player_id}`}>
            <span>{entry.display_name ?? entry.discord_username}</span>
            <span>{entry.wins}</span>
            <span>{entry.kills}</span>
            <span>{entry.deaths}</span>
            <span>{entry.assists}</span>
            <span>{entry.damage}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}


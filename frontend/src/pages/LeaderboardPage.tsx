import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { LeaderboardEntry } from "../api/types";

interface LeaderboardPageProps {
  entries: LeaderboardEntry[];
}

type SortKey = keyof Pick<
  LeaderboardEntry,
  | "matches_played"
  | "wins"
  | "draws"
  | "losses"
  | "win_percentage"
  | "average_kills"
  | "average_assists"
  | "average_deaths"
  | "kill_death_ratio"
  | "damage_per_minute"
>;

const columns: Array<{ key: SortKey; label: string; title?: string }> = [
  { key: "matches_played", label: "MP", title: "Matches played" },
  { key: "wins", label: "W", title: "Wins" },
  { key: "draws", label: "D", title: "Draws" },
  { key: "losses", label: "L", title: "Losses" },
  { key: "win_percentage", label: "Win%", title: "Wins divided by wins plus losses" },
  { key: "average_kills", label: "K/G", title: "Average kills per game" },
  { key: "average_assists", label: "A/G", title: "Average assists per game" },
  { key: "average_deaths", label: "D/G", title: "Average deaths per game" },
  { key: "kill_death_ratio", label: "K/D", title: "Kill/death ratio" },
  { key: "damage_per_minute", label: "DPM", title: "Damage per non-Medic minute" },
];

const format = (value: number) => value.toFixed(1);

export function LeaderboardPage({ entries }: LeaderboardPageProps) {
  const [minimumGames, setMinimumGames] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>("matches_played");
  const [descending, setDescending] = useState(true);

  const visibleEntries = useMemo(
    () =>
      entries
        .filter((entry) => entry.matches_played >= minimumGames)
        .sort((left, right) => {
          const difference = left[sortKey] - right[sortKey];
          return descending ? -difference : difference;
        }),
    [descending, entries, minimumGames, sortKey],
  );

  const selectSort = (key: SortKey) => {
    if (key === sortKey) setDescending((value) => !value);
    else {
      setSortKey(key);
      setDescending(true);
    }
  };

  return (
    <section className="panel leaderboard-panel">
      <div className="panel-header leaderboard-header">
        <div>
          <h1>Leaderboard</h1>
          <span>{visibleEntries.length} of {entries.length} tracked players</span>
        </div>
        <label className="minimum-games">
          Minimum games
          <input
            type="number"
            min="0"
            value={minimumGames}
            onChange={(event) => setMinimumGames(Math.max(0, Number(event.target.value) || 0))}
          />
        </label>
      </div>
      <div className="leaderboard-scroll">
        <table className="leaderboard-table">
          <thead>
            <tr>
              <th>Player</th>
              {columns.map((column) => (
                <th key={column.key} title={column.title}>
                  <button className="sort-button" onClick={() => selectSort(column.key)}>
                    {column.label}{sortKey === column.key ? (descending ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleEntries.map((entry) => (
              <tr key={entry.player_id}>
                <td><Link to={`/players/${entry.player_id}`}>{entry.display_name ?? entry.discord_username}</Link></td>
                <td>{entry.matches_played}</td>
                <td>{entry.wins}</td>
                <td>{entry.draws}</td>
                <td>{entry.losses}</td>
                <td>{format(entry.win_percentage)}%</td>
                <td>{format(entry.average_kills)}</td>
                <td>{format(entry.average_assists)}</td>
                <td>{format(entry.average_deaths)}</td>
                <td>{format(entry.kill_death_ratio)}</td>
                <td>{Math.round(entry.damage_per_minute)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

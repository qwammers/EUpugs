import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { LeaderboardEntry } from "../api/types";

interface LeaderboardPageProps {
  entries: LeaderboardEntry[];
}

type SortKey = keyof Pick<
  LeaderboardEntry,
  | "matches_played"
  | "wins"
  | "losses"
  | "win_percentage"
  | "average_kills"
  | "average_assists"
  | "average_deaths"
  | "kill_death_ratio"
  | "damage_per_minute"
>;

const columns: Array<{ key: SortKey; label: string; title: string }> = [
  { key: "matches_played", label: "MP", title: "Matches played" },
  { key: "wins", label: "W", title: "Wins" },
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
  const [search, setSearch] = useState("");
  const [className, setClassName] = useState("");
  const [classEntries, setClassEntries] = useState<LeaderboardEntry[] | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("matches_played");
  const [descending, setDescending] = useState(true);
  useEffect(() => {
    if (!className) {
      setClassEntries(null);
      return;
    }
    void api.getLeaderboard(className).then(setClassEntries);
  }, [className]);
  const sourceEntries = classEntries ?? entries;
  const visibleEntries = useMemo(
    () => sourceEntries.filter((entry) => {
      const name = entry.display_name ?? entry.discord_username;
      return entry.matches_played >= minimumGames
        && name.toLowerCase().includes(search.trim().toLowerCase());
    }).sort((left, right) => {
      const difference = left[sortKey] - right[sortKey];
      return descending ? -difference : difference;
    }),
    [descending, minimumGames, search, sortKey, sourceEntries],
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
        <div><h1>Leaderboard</h1><span>{visibleEntries.length} of {sourceEntries.length} tracked players</span></div>
        <label className="minimum-games">
          Search
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Player name" />
        </label>
        <label className="minimum-games">
          Minimum games
          <input type="number" min="0" value={minimumGames} onChange={(event) => setMinimumGames(Math.max(0, Number(event.target.value) || 0))} />
        </label>
      </div>
      <div className="class-filter-row">
        {["", "scout", "soldier", "demoman", "medic"].map((value) => (
          <button className={className === value ? "selected" : ""} key={value || "all"} onClick={() => setClassName(value)}>
            {value || "All classes"}
          </button>
        ))}
      </div>
      <div className="leaderboard-scroll">
        <table className="leaderboard-table">
          <thead><tr><th>Player</th>{columns.map((column) => (
            <th key={column.key} title={column.title}><button className="sort-button" onClick={() => selectSort(column.key)}>
              {column.label}{sortKey === column.key ? (descending ? " v" : " ^") : ""}
            </button></th>
          ))}</tr></thead>
          <tbody>{visibleEntries.map((entry) => (
            <tr key={entry.player_id}>
              <td><Link to={`/players/${entry.player_id}`}>{entry.display_name ?? entry.discord_username}</Link></td>
              <td>{entry.matches_played}</td><td>{entry.wins}</td><td>{entry.losses}</td>
              <td className={entry.win_percentage >= 50 ? "win-rate-good" : "win-rate-bad"}>{format(entry.win_percentage)}%</td>
              <td>{format(entry.average_kills)}</td><td>{format(entry.average_assists)}</td>
              <td>{format(entry.average_deaths)}</td><td>{format(entry.kill_death_ratio)}</td>
              <td>{Math.round(entry.damage_per_minute)}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

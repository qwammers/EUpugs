import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Etf2lReview, MatchRead, MeResponse, QueueState } from "../api/types";

export function AdminPage({
  me, queue, activeMatches, refreshAll,
}: {
  me: MeResponse | null;
  queue: QueueState | null;
  activeMatches: MatchRead[];
  refreshAll: () => Promise<void>;
}) {
  const [reviews, setReviews] = useState<Etf2lReview[]>([]);
  const [tiers, setTiers] = useState<Record<number, string>>({});
  const [logInputs, setLogInputs] = useState<Record<number, string>>({});
  const [subInputs, setSubInputs] = useState<Record<number, { outgoing: string; incoming: string }>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me?.is_admin) void api.getEtf2lReviews().then(setReviews);
  }, [me?.is_admin]);

  const run = async (task: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await task();
      await refreshAll();
      setMessage(success);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!me?.is_admin) return <section className="panel">
    <h1>Admin Dashboard</h1><p className="muted">A configured runner role is required.</p>
  </section>;

  return <div className="page-grid">
    <section className="panel">
      <div className="panel-header"><h1>Match control</h1><span>{activeMatches.length} active</span></div>
      <p>Current queue: Match #{queue?.match_id ?? "..."}, {queue?.queue.count ?? 0} players</p>
      {message && <p className="message">{message}</p>}
    </section>
    {activeMatches.map((match) => <section className="panel" key={match.id}>
      <div className="panel-header">
        <h2>Match #{match.id}</h2>
        <span className="pill">{match.status} · setup {match.discord_setup ?? "waiting"}</span>
      </div>
      <p>{match.map_name ?? "Map pending"} · RED {Math.round(match.team_average_elo.RED ?? 0)} Elo · BLU {Math.round(match.team_average_elo.BLU ?? 0)} Elo</p>
      <div className="button-row">
        <button disabled={busy || match.status !== "ready" || !match.discord_setup}
          onClick={() => void run(() => api.updateMatchState(match.id, "live"), "Match started.")}>Start live</button>
        <button disabled={busy} onClick={() => void run(
          () => api.updateMatchState(match.id, "awaiting_log"), "Waiting for log.",
        )}>Await log</button>
        <button disabled={busy} onClick={() => void run(
          () => api.updateMatchState(match.id, "completed"), "Match completed.",
        )}>Complete</button>
        <button disabled={busy} onClick={() => void run(
          () => api.updateMatchState(match.id, "cancelled"), "Match cancelled.",
        )}>Cancel</button>
      </div>
      <label>Log ID or URL<input
        value={logInputs[match.id] ?? ""}
        onChange={(event) => setLogInputs((current) => ({ ...current, [match.id]: event.target.value }))}
      /></label>
      <button disabled={busy || !logInputs[match.id]} onClick={() => void run(
        () => api.attachLog(match.id, logInputs[match.id]), "Log attached.",
      )}>Attach log</button>
      {match.status === "live" && <>
        <h3>Substitution</h3>
        <div className="button-row">
          <input placeholder="Outgoing player ID" value={subInputs[match.id]?.outgoing ?? ""}
            onChange={(event) => setSubInputs((current) => ({
              ...current, [match.id]: { outgoing: event.target.value, incoming: current[match.id]?.incoming ?? "" },
            }))} />
          <input placeholder="Queued player ID" value={subInputs[match.id]?.incoming ?? ""}
            onChange={(event) => setSubInputs((current) => ({
              ...current, [match.id]: { outgoing: current[match.id]?.outgoing ?? "", incoming: event.target.value },
            }))} />
          <button disabled={busy || !subInputs[match.id]?.outgoing || !subInputs[match.id]?.incoming}
            onClick={() => void run(() => api.substitute(
              match.id,
              Number(subInputs[match.id].outgoing),
              Number(subInputs[match.id].incoming),
            ), "Substitution recorded.")}>Replace player</button>
        </div>
      </>}
    </section>)}
    <section className="panel">
      <div className="panel-header"><h2>ETF2L skill review</h2><span>{reviews.length} pending</span></div>
      <div className="archive-list">{reviews.map((review) => <div className="review-row" key={review.player_id}>
        <div><strong>{review.display_name}</strong><p>Recent: {review.recent_division ?? "none"} · Highest: {review.highest_division ?? "none"}</p></div>
        <select value={tiers[review.player_id] ?? ""} onChange={(event) =>
          setTiers((current) => ({ ...current, [review.player_id]: event.target.value }))
        }>
          <option value="">Choose tier</option>
          {["Obsidian", "Sapphire", "Silver", "Bronze", "Steel", "Iron"].map((tier) =>
            <option key={tier} value={tier.toLowerCase()}>{tier}</option>)}
        </select>
        <div className="button-row">
          <button disabled={busy || !tiers[review.player_id]} onClick={() => void run(
            () => api.decideEtf2l(review.player_id, "accepted", tiers[review.player_id]).then(() =>
              setReviews((current) => current.filter((item) => item.player_id !== review.player_id))
            ), "Tier approved and Elo seeded.",
          )}>Approve tier</button>
          <button disabled={busy} onClick={() => void run(
            () => api.decideEtf2l(review.player_id, "rejected"), "Player rejected.",
          )}>Reject</button>
        </div>
      </div>)}</div>
    </section>
  </div>;
}

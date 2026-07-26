import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Etf2lReview, MatchRead, MeResponse, QueueState } from "../api/types";

interface AdminPageProps {
  me: MeResponse | null;
  queue: QueueState | null;
  currentMatch: MatchRead | null;
  refreshAll: () => Promise<void>;
}

export function AdminPage({ me, queue, currentMatch, refreshAll }: AdminPageProps) {
  const [mapName, setMapName] = useState("");
  const [mapCandidates, setMapCandidates] = useState(["", "", ""]);
  const [outgoingPlayerId, setOutgoingPlayerId] = useState("");
  const [incomingPlayerId, setIncomingPlayerId] = useState("");
  const [reviews, setReviews] = useState<Etf2lReview[]>([]);
  const [logInput, setLogInput] = useState("");
  const [playerId, setPlayerId] = useState("");
  const [playerUsername, setPlayerUsername] = useState("");
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

  if (!me?.is_admin) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h1>Admin Dashboard</h1>
        </div>
        <p className="muted">An admin role from Discord is required to use this page.</p>
      </section>
    );
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>Admin Dashboard</h1>
          <span className="pill pill-good">Admin</span>
        </div>
        <p className="muted">
          Create matches from the current queue, move state forward, and attach logs.tf results.
        </p>
        <label>
          Map name
          <input value={mapName} onChange={(event) => setMapName(event.target.value)} placeholder="cp_process_f12" />
        </label>
        <div className="button-row">
          <button
            disabled={busy || !queue?.matchable}
            onClick={() => void run(() => api.createMatch(mapName || undefined), "Created a match from the queue.")}
          >
            Create match
          </button>
          {currentMatch && (
            <>
              <button
                disabled={busy}
                onClick={() =>
                  void run(() => api.updateMatchState(currentMatch.id, "live"), "Moved the match to live.")
                }
              >
                Set live
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(
                    () => api.updateMatchState(currentMatch.id, "awaiting_log"),
                    "Moved the match to awaiting_log.",
                  )
                }
              >
                Awaiting log
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(
                    () => api.updateMatchState(currentMatch.id, "completed"),
                    "Marked the match completed.",
                  )
                }
              >
                Complete
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(
                    () => api.updateMatchState(currentMatch.id, "cancelled"),
                    "Cancelled the match.",
                  )
                }
              >
                Cancel
              </button>
            </>
          )}
        </div>
        {message && <p className="message">{message}</p>}
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>Attach logs.tf result</h2>
        </div>
        <label>
          Log ID or URL
          <input value={logInput} onChange={(event) => setLogInput(event.target.value)} placeholder="https://logs.tf/123456" />
        </label>
        <div className="button-row">
          <button
            disabled={busy || !currentMatch || !logInput}
            onClick={() =>
              void run(() => api.attachLog(currentMatch!.id, logInput), "Attached the log and ingested stats.")
            }
          >
            Attach log
          </button>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header"><h2>Map vote candidates</h2></div>
        {mapCandidates.map((value, index) => <input
          key={index}
          value={value}
          placeholder={`Map ${index + 1}`}
          onChange={(event) => setMapCandidates((current) =>
            current.map((item, itemIndex) => itemIndex === index ? event.target.value : item)
          )}
        />)}
        <div className="button-row"><button disabled={busy || mapCandidates.some((item) => !item.trim())}
          onClick={() => void run(() => api.setMapCandidates(mapCandidates), "Updated map vote.")}>
          Open map vote
        </button></div>
      </section>
      <section className="panel">
        <div className="panel-header"><h2>Live substitution</h2></div>
        <label>Outgoing player ID<input value={outgoingPlayerId} onChange={(event) => setOutgoingPlayerId(event.target.value)} /></label>
        <label>Next-queue player ID<input value={incomingPlayerId} onChange={(event) => setIncomingPlayerId(event.target.value)} /></label>
        <div className="button-row"><button disabled={busy || !currentMatch || !outgoingPlayerId || !incomingPlayerId}
          onClick={() => void run(
            () => api.substitute(currentMatch!.id, Number(outgoingPlayerId), Number(incomingPlayerId)),
            "Substitution recorded.",
          )}>Accept substitute</button></div>
      </section>
      <section className="panel">
        <div className="panel-header"><h2>ETF2L reviews</h2><span>{reviews.length} pending</span></div>
        <div className="archive-list">{reviews.map((review) => <div className="archive-row" key={review.player_id}>
          <strong>{review.display_name}</strong>
          <span>{review.highest_division ?? "Unknown division"}</span>
          {review.profile_url ? <a href={review.profile_url} target="_blank" rel="noreferrer">ETF2L</a> : <span>No profile</span>}
          <div className="button-row">
            <button disabled={busy} onClick={() => void run(
              () => api.decideEtf2l(review.player_id, "accepted").then(() =>
                setReviews((current) => current.filter((item) => item.player_id !== review.player_id))
              ), "Player accepted.",
            )}>Accept</button>
            <button disabled={busy} onClick={() => void run(
              () => api.decideEtf2l(review.player_id, "rejected").then(() =>
                setReviews((current) => current.filter((item) => item.player_id !== review.player_id))
              ), "Player rejected.",
            )}>Reject</button>
          </div>
        </div>)}</div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>Queue Summary</h2>
        </div>
        <p>Active queue: {queue?.active.count ?? 0}/12</p>
        <p>Next queue: {queue?.next.count ?? 0}</p>
        <p>Current match: {currentMatch ? `#${currentMatch.id} (${currentMatch.status})` : "none"}</p>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>Player username</h2>
        </div>
        <label>
          Player ID
          <input type="number" min="1" value={playerId} onChange={(event) => setPlayerId(event.target.value)} />
        </label>
        <label>
          Static site username
          <input value={playerUsername} onChange={(event) => setPlayerUsername(event.target.value)} maxLength={100} />
        </label>
        <div className="button-row">
          <button
            disabled={busy || !playerId || !playerUsername.trim()}
            onClick={() => void run(
              () => api.updatePlayerUsername(Number(playerId), playerUsername),
              "Updated and locked the player's site username.",
            )}
          >
            Update username
          </button>
        </div>
      </section>
    </div>
  );
}

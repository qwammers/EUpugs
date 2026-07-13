import { useState } from "react";
import { api } from "../api/client";
import type { MatchRead, MeResponse, QueueState } from "../api/types";

interface AdminPageProps {
  me: MeResponse | null;
  queue: QueueState | null;
  currentMatch: MatchRead | null;
  refreshAll: () => Promise<void>;
}

export function AdminPage({ me, queue, currentMatch, refreshAll }: AdminPageProps) {
  const [mapName, setMapName] = useState("");
  const [logInput, setLogInput] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
        <div className="panel-header">
          <h2>Queue Summary</h2>
        </div>
        <p>Active queue: {queue?.active.count ?? 0}/12</p>
        <p>Next queue: {queue?.next.count ?? 0}</p>
        <p>Current match: {currentMatch ? `#${currentMatch.id} (${currentMatch.status})` : "none"}</p>
      </section>
    </div>
  );
}


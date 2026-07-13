import { useState } from "react";
import { api } from "../api/client";
import type { MeResponse, QueueState } from "../api/types";
import { QueueCard } from "../components/QueueCard";

interface QueuePageProps {
  me: MeResponse | null;
  queue: QueueState | null;
  refreshQueue: () => Promise<void>;
}

export function QueuePage({ me, queue, refreshQueue }: QueuePageProps) {
  const [selectedClasses, setSelectedClasses] = useState<string[]>(["scout"]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const toggleClass = (value: string) => {
    setSelectedClasses((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  };

  const join = async (bucket: "active" | "next") => {
    setBusy(true);
    setMessage(null);
    try {
      await api.joinQueue(selectedClasses, bucket);
      await refreshQueue();
      setMessage(`Joined the ${bucket} queue.`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const leave = async (bucket: "active" | "next") => {
    setBusy(true);
    setMessage(null);
    try {
      await api.leaveQueue(bucket);
      await refreshQueue();
      setMessage(`Left the ${bucket} queue.`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setReady = async (ready: boolean) => {
    setBusy(true);
    setMessage(null);
    try {
      await api.setReady(ready);
      await refreshQueue();
      setMessage(ready ? "Ready check updated." : "Ready state cleared.");
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-grid">
      <section className="panel">
        <div className="panel-header">
          <h1>Queue Controls</h1>
          <span className="pill pill-info">{me ? "Authenticated" : "Public view"}</span>
        </div>
        {!me ? (
          <p className="muted">Log in with Discord to join the queue and ready up.</p>
        ) : (
          <>
            <p className="muted">
              Choose one or more TF2 6s classes. Steam must be linked through Discord connections.
            </p>
            <div className="class-picker">
              {["scout", "soldier", "demo", "medic"].map((className) => (
                <label className="class-chip" key={className}>
                  <input
                    checked={selectedClasses.includes(className)}
                    onChange={() => toggleClass(className)}
                    type="checkbox"
                  />
                  {className}
                </label>
              ))}
            </div>
            <div className="button-row">
              <button disabled={busy || selectedClasses.length === 0} onClick={() => void join("active")}>
                Join active queue
              </button>
              <button disabled={busy || selectedClasses.length === 0} onClick={() => void join("next")}>
                Queue next match
              </button>
              <button disabled={busy} onClick={() => void leave("active")}>
                Leave active
              </button>
              <button disabled={busy} onClick={() => void leave("next")}>
                Leave next
              </button>
              <button disabled={busy} onClick={() => void setReady(true)}>
                Ready
              </button>
              <button disabled={busy} onClick={() => void setReady(false)}>
                Unready
              </button>
            </div>
            {message && <p className="message">{message}</p>}
          </>
        )}
      </section>
      {queue && <QueueCard bucket={queue.active} />}
      {queue && <QueueCard bucket={queue.next} />}
      {queue && (
        <section className="panel">
          <div className="panel-header">
            <h2>Needed by class</h2>
          </div>
          <div className="stat-grid">
            {Object.entries(queue.needed_by_class).map(([className, count]) => (
              <div key={className}>
                <strong>{count}</strong>
                <span>{className}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}


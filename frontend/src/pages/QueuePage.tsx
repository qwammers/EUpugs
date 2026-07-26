import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MeResponse, QueueState } from "../api/types";
import { QueueCard } from "../components/QueueCard";

const classes = ["scout", "soldier", "demo", "medic"];

interface QueuePageProps {
  me: MeResponse | null;
  queue: QueueState | null;
  refreshQueue: () => Promise<void>;
}

const secondsRemaining = (value: string | null | undefined, now: number) =>
  value ? Math.max(0, Math.ceil((new Date(value).getTime() - now) / 1000)) : 0;

export function QueuePage({ me, queue, refreshQueue }: QueuePageProps) {
  const [primaryClass, setPrimaryClass] = useState("scout");
  const [flexClasses, setFlexClasses] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const heardCheck = useRef<string | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
      void refreshQueue();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshQueue]);

  useEffect(() => {
    if (!queue?.ready_check_id || heardCheck.current === queue.ready_check_id) return;
    heardCheck.current = queue.ready_check_id;
    const AudioContextClass = window.AudioContext;
    const context = new AudioContextClass();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 660;
    gain.gain.setValueAtTime(0.15, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.7);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.7);
  }, [queue?.ready_check_id]);

  const run = async (task: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await task();
      await refreshQueue();
      setMessage(success);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleFlex = (className: string) => {
    setFlexClasses((current) =>
      current.includes(className)
        ? current.filter((item) => item !== className)
        : [...current, className],
    );
  };

  const myEntry = queue?.active.players.find((item) => item.player_id === me?.player.id);
  const readySeconds = secondsRemaining(queue?.ready_check_expires_at, now);
  const preReadySeconds = secondsRemaining(myEntry?.pre_ready_expires_at, now);

  return (
    <div className="page-grid">
      <section className="panel queue-control-panel">
        <div className="panel-header">
          <h1>Choose your role</h1>
          <span className={`pill ${queue?.phase === "ready_check" ? "pill-warn" : "pill-info"}`}>
            {queue?.phase === "ready_check" ? `READY ${readySeconds}s` : "Queue open"}
          </span>
        </div>
        {!me ? <p className="muted">Log in with Discord to join and ready up.</p> : <>
          <p className="muted">Pick one primary class. Flex choices are only used when needed.</p>
          <div className="primary-class-grid">
            {classes.map((className) => {
              const blocked = queue?.blocked_classes.includes(className);
              return <button
                className={`class-select ${primaryClass === className ? "selected" : ""}`}
                disabled={busy || blocked}
                key={className}
                onClick={() => {
                  setPrimaryClass(className);
                  setFlexClasses((current) => current.filter((item) => item !== className));
                }}
              >
                <strong>{className}</strong>
                <span>{blocked ? "Restricted" : `${queue?.needed_by_class[className] ?? 0} needed`}</span>
              </button>;
            })}
          </div>
          <h3>Flex slots</h3>
          <div className="class-picker">
            {classes.filter((item) => item !== primaryClass).map((className) => (
              <label className="class-chip" key={className}>
                <input
                  checked={flexClasses.includes(className)}
                  disabled={queue?.blocked_classes.includes(className)}
                  onChange={() => toggleFlex(className)}
                  type="checkbox"
                />
                {className}
              </label>
            ))}
          </div>
          <div className="button-row">
            <button disabled={busy} onClick={() => void run(
              () => api.joinQueue(primaryClass, flexClasses, "active"), "Joined active queue.",
            )}>Join active</button>
            <button disabled={busy} onClick={() => void run(
              () => api.joinQueue(primaryClass, flexClasses, "next"), "Queued for next match.",
            )}>Queue next</button>
            <button disabled={busy || !myEntry} onClick={() => void run(
              () => api.setPreReady(), "Pre-ready enabled for 3 minutes.",
            )}>Pre-ready {preReadySeconds > 0 ? `(${preReadySeconds}s)` : ""}</button>
            <button disabled={busy || queue?.phase !== "ready_check"} onClick={() => void run(
              () => api.setReady(true), "Ready confirmed.",
            )}>Ready</button>
            <button disabled={busy} onClick={() => void run(
              () => api.leaveQueue("active"), "Left active queue.",
            )}>Leave active</button>
          </div>
          {message && <p className="message">{message}</p>}
        </>}
      </section>

      {queue && <QueueCard bucket={queue.active} />}
      {queue && <QueueCard bucket={queue.next} />}

      {queue && queue.map_candidates.length > 0 && <section className="panel">
        <div className="panel-header"><h2>Map vote</h2></div>
        <div className="map-vote-grid">
          {queue.map_candidates.map((mapName) => (
            <button disabled={busy || !myEntry} key={mapName} onClick={() => void run(
              () => api.voteMap(mapName), `Voted for ${mapName}.`,
            )}>
              <strong>{mapName}</strong>
              <span>{queue.map_votes[mapName] ?? 0} votes</span>
            </button>
          ))}
        </div>
      </section>}
    </div>
  );
}

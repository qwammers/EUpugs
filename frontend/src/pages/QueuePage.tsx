import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MeResponse, QueueState } from "../api/types";
import { QueueCard } from "../components/QueueCard";

const classes = ["scout", "soldier", "demo", "medic"];
const secondsRemaining = (value: string | null | undefined, now: number) =>
  value ? Math.max(0, Math.ceil((new Date(value).getTime() - now) / 1000)) : 0;

export function QueuePage({
  me, queue, refreshQueue,
}: {
  me: MeResponse | null;
  queue: QueueState | null;
  refreshQueue: () => Promise<void>;
}) {
  const [primaryClass, setPrimaryClass] = useState("scout");
  const [flexClasses, setFlexClasses] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const heardCheck = useRef<string | null>(null);
  const myEntry = queue?.queue.players.find((item) => item.player_id === me?.player.id);

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
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 660;
    gain.gain.setValueAtTime(0.15, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.7);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.7);
  }, [queue?.ready_check_id]);

  useEffect(() => {
    if (myEntry) {
      setPrimaryClass(myEntry.primary_class);
      setFlexClasses(myEntry.flex_classes);
    }
  }, [myEntry?.player_id, myEntry?.primary_class]);

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

  const choosePrimary = (className: string) => {
    const nextFlex = flexClasses.filter((item) => item !== className);
    setPrimaryClass(className);
    setFlexClasses(nextFlex);
    void run(() => api.setPrimary(className, nextFlex), `Queued as ${className}.`);
  };

  const toggleFlex = (className: string) => {
    const next = flexClasses.includes(className)
      ? flexClasses.filter((item) => item !== className)
      : [...flexClasses, className];
    setFlexClasses(next);
    if (myEntry) void run(() => api.setFlex(next), "Flex choices updated.");
  };

  const removePlayer = (playerId: number) => void run(
    () => api.removeQueuedPlayer(playerId), "Player removed from queue.",
  );
  const readySeconds = secondsRemaining(queue?.ready_check_expires_at, now);
  const preReadySeconds = secondsRemaining(myEntry?.pre_ready_expires_at, now);

  return <div className="page-grid">
    <section className="panel queue-control-panel">
      <div className="panel-header">
        <div><h1>Match #{queue?.match_id ?? "..."}</h1><span>Click a class to queue or switch</span></div>
        <span className={`pill ${queue?.phase === "ready_check" ? "pill-warn" : "pill-info"}`}>
          {queue?.phase === "ready_check" ? `READY ${readySeconds}s` : "Forming"}
        </span>
      </div>
      {!me ? <p className="muted">Log in with Discord to queue.</p> : <>
        <div className="primary-class-grid">
          {classes.map((className) => <button
            className={`class-select ${myEntry?.primary_class === className ? "selected" : ""}`}
            disabled={busy || queue?.blocked_classes.includes(className)}
            key={className}
            onClick={() => choosePrimary(className)}
          ><strong>{className}</strong><span>{queue?.needed_by_class[className] ?? 0} needed</span></button>)}
        </div>
        <h3>Flex slots</h3>
        <div className="class-picker">{classes.filter((item) => item !== primaryClass).map((className) =>
          <label className="class-chip" key={className}><input
            checked={flexClasses.includes(className)}
            disabled={!myEntry || busy || queue?.blocked_classes.includes(className)}
            onChange={() => toggleFlex(className)}
            type="checkbox"
          />{className}</label>)}</div>
        <div className="button-row">
          <button disabled={busy || !myEntry} onClick={() => void run(
            () => api.setPreReady(), "Pre-ready enabled for 3 minutes.",
          )}>Pre-ready {preReadySeconds > 0 ? `(${preReadySeconds}s)` : ""}</button>
          <button disabled={busy || queue?.phase !== "ready_check"} onClick={() => void run(
            () => api.setReady(true), "Ready confirmed.",
          )}>Ready</button>
          <button disabled={busy || !myEntry} onClick={() => void run(
            () => api.leaveQueue(), "Left queue.",
          )}>Leave queue</button>
        </div>
        {message && <p className="message">{message}</p>}
      </>}
    </section>
    {queue && <QueueCard
      bucket={queue.queue}
      isAdmin={Boolean(me?.is_admin)}
      onRemove={removePlayer}
    />}
    {queue && <section className="panel">
      <div className="panel-header"><h2>Map vote</h2><span>Three random maps</span></div>
      <div className="map-vote-grid">{queue.map_candidates.map((mapName) => <button
        disabled={busy || !myEntry}
        key={mapName}
        onClick={() => void run(() => api.voteMap(mapName), `Voted for ${mapName}.`)}
      ><strong>{mapName}</strong><span>{queue.map_votes[mapName] ?? 0} votes</span></button>)}</div>
    </section>}
  </div>;
}
